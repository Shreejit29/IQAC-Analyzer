from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any

import fitz  # PyMuPDF
from PIL import Image, ImageStat


NOT_IDENTIFIED = "Not Identified"


@dataclass
class ExtractedPhoto:
    image_bytes: bytes
    image_ext: str
    report_name: str
    source_page: int
    activity_title: str
    activity_date: str
    activity_time: str
    venue: str


_CLOCK = r"(?:[0-9]{1,2}[.:][0-9]{2}|[0-9]{1,2})\s*(?:a\.m\.?|p\.m\.?|am|pm)"
_TIME_PATTERNS = [
    re.compile(rf"\b(?:time|timing)\s*[:\-]?\s*({_CLOCK}(?:\s*(?:to|[-–]|onwards)\s*{_CLOCK})?)\b", re.I),
    re.compile(rf"(?<![0-9.])\b({_CLOCK})\b", re.I),
]


def _clean(value: Any) -> str:
    if value is None:
        return NOT_IDENTIFIED
    text = " ".join(str(value).split()).strip()
    return text or NOT_IDENTIFIED


def _page_range(value: str) -> list[int]:
    text = _clean(value)
    if text == NOT_IDENTIFIED:
        return []
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if not nums:
        return []
    if len(nums) == 1:
        return nums
    start, end = nums[0], nums[1]
    if 1 <= start <= end <= 10000 and end - start <= 100:
        return list(range(start, end + 1))
    return [start]


def _activity_matches_page(record: dict[str, Any], page_no: int, page_text: str) -> int:
    score = 0
    source_pages = _page_range(_clean(record.get("Source Page")))
    if page_no in source_pages:
        score += 8
    title = _clean(record.get("Activity Title"))
    venue = _clean(record.get("Venue"))
    date = _clean(record.get("Activity Date"))
    haystack = page_text.lower()
    for value, weight in ((title, 7), (venue, 3), (date, 2)):
        if value != NOT_IDENTIFIED and len(value) >= 4:
            key = value.lower()
            if key in haystack:
                score += weight
            else:
                words = [w for w in re.findall(r"[a-zA-Z0-9]+", key) if len(w) >= 5]
                hits = sum(1 for word in words if word in haystack)
                if hits >= max(1, min(3, len(words) // 2)):
                    score += weight // 2
    return score


def _best_record(records: list[dict[str, Any]], report_name: str, page_no: int, page_text: str) -> dict[str, Any] | None:
    candidates = [r for r in records if _clean(r.get("Source Report")) == _clean(report_name)]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    scored = [(r, _activity_matches_page(r, page_no, page_text)) for r in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored and scored[0][1] > 0 else None


def _page_time(page_texts: list[str], preferred_pages: list[int]) -> str:
    search_order: list[int] = []
    for p in preferred_pages:
        if 1 <= p <= len(page_texts) and p not in search_order:
            search_order.append(p)
    for p in preferred_pages:
        for delta in (1, -1, 2, -2):
            q = p + delta
            if 1 <= q <= len(page_texts) and q not in search_order:
                search_order.append(q)
    search_order.extend(p for p in range(1, len(page_texts) + 1) if p not in search_order)

    for p in search_order:
        text = page_texts[p - 1]
        for pattern in _TIME_PATTERNS:
            match = pattern.search(text)
            if match:
                return _clean(match.group(1))
    return NOT_IDENTIFIED


def _is_color_photo(image_bytes: bytes, min_dimension: int = 300, color_threshold: float = 8.0) -> bool:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
            if min(width, height) < min_dimension:
                return False
            if image.mode not in {"RGB", "RGBA", "CMYK", "P", "LA"}:
                return False
            rgb = image.convert("RGB")
            # Downsample for a quick, memory-safe color test.
            rgb.thumbnail((120, 120))
            stat = ImageStat.Stat(rgb)
            channel_means = stat.mean
            channel_spread = max(channel_means) - min(channel_means)
            if channel_spread >= color_threshold:
                return True

            # Some photographs have balanced average RGB channels. Sample pixels
            # and require a meaningful fraction with chroma above the threshold.
            pixels = list(rgb.getdata())
            if not pixels:
                return False
            step = max(1, len(pixels) // 2000)
            sampled = pixels[::step]
            colorful = 0
            for r, g, b in sampled:
                if max(r, g, b) - min(r, g, b) >= 14:
                    colorful += 1
            return (colorful / len(sampled)) >= 0.03
    except Exception:
        return False


def _extract_page_images(page: fitz.Page) -> list[tuple[bytes, str]]:
    found: list[tuple[bytes, str]] = []
    seen_xrefs: set[int] = set()
    page_area = max(page.rect.width * page.rect.height, 1.0)
    for img in page.get_images(full=True):
        xref = int(img[0])
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        try:
            info = page.parent.extract_image(xref)
            image_bytes = info.get("image")
            ext = str(info.get("ext") or "png").lower()
            if not image_bytes or not _is_color_photo(image_bytes):
                continue

            # Ignore full-page scans/forms and tiny decorative elements. A
            # normal activity photograph is typically a medium/large image
            # that occupies only part of the report page.
            rects = page.get_image_rects(xref, transform=False)
            if rects:
                largest = max((r.width * r.height) / page_area for r in rects)
                if largest > 0.78:
                    continue

            with Image.open(io.BytesIO(image_bytes)) as image:
                width, height = image.size
            aspect = width / max(height, 1)
            if aspect < 0.45 or aspect > 2.8:
                continue

            found.append((image_bytes, ext))
        except Exception:
            continue
    return found


def extract_color_photos(
    documents: list[tuple[bytes, str]],
    records: list[dict[str, Any]],
) -> list[ExtractedPhoto]:
    """Extract embedded color photographs from uploaded PDF reports.

    Photos are associated, where possible, with the activity record whose source
    page/title/date/venue best matches the photograph's report page.
    """
    extracted: list[ExtractedPhoto] = []
    global_image_hashes: set[str] = set()
    for raw, filename in documents:
        if not filename.lower().endswith(".pdf"):
            continue
        try:
            doc = fitz.open(stream=raw, filetype="pdf")
        except Exception:
            continue
        try:
            page_texts = [(page.get_text("text") or "").strip() for page in doc]
            for page_index, page in enumerate(doc, start=1):
                page_text = page_texts[page_index - 1] if page_index <= len(page_texts) else ""
                record = _best_record(records, filename, page_index, page_text)
                preferred_pages = _page_range(_clean(record.get("Source Page"))) if record else [page_index]
                activity_time = (
                    _clean(record.get("Activity Time"))
                    if record and _clean(record.get("Activity Time")) != NOT_IDENTIFIED
                    else _page_time(page_texts, preferred_pages)
                )
                if not record:
                    record = {}

                for image_bytes, ext in _extract_page_images(page):
                    image_hash = hashlib.sha1(image_bytes).hexdigest()
                    if image_hash in global_image_hashes:
                        continue
                    global_image_hashes.add(image_hash)
                    extracted.append(
                        ExtractedPhoto(
                            image_bytes=image_bytes,
                            image_ext=ext,
                            report_name=filename,
                            source_page=page_index,
                            activity_title=_clean(record.get("Activity Title")),
                            activity_date=_clean(record.get("Activity Date")),
                            activity_time=activity_time,
                            venue=_clean(record.get("Venue")),
                        )
                    )
        finally:
            doc.close()
    return extracted


def build_photo_evidence_pdf(photos: list[ExtractedPhoto]) -> bytes:
    """Create one A4 page per extracted color photograph."""
    out = fitz.open()
    page_width, page_height = fitz.paper_size("a4")
    margin = 36
    text_height = 138

    for idx, photo in enumerate(photos, start=1):
        page = out.new_page(width=page_width, height=page_height)
        page.draw_rect(
            fitz.Rect(0, 0, page_width, page_height),
            color=(0.91, 0.94, 0.97),
            fill=(0.99, 0.995, 1.0),
            width=0.5,
        )
        title_rect = fitz.Rect(margin, margin, page_width - margin, margin + 26)
        page.insert_textbox(
            title_rect,
            "IQAC — Color Photo Evidence",
            fontname="hebo",
            fontsize=17,
            color=(0.06, 0.18, 0.30),
            align=0,
        )

        metadata = (
            f"Activity: {photo.activity_title}\n"
            f"Date: {photo.activity_date}    |    Time: {photo.activity_time}\n"
            f"Venue: {photo.venue}\n"
            f"Source Report: {photo.report_name}    |    Source Page: {photo.source_page}"
        )
        meta_rect = fitz.Rect(margin, margin + 30, page_width - margin, margin + text_height)
        page.insert_textbox(
            meta_rect,
            metadata,
            fontname="helv",
            fontsize=9.5,
            lineheight=1.2,
            color=(0.18, 0.25, 0.32),
            align=0,
        )

        image_rect = fitz.Rect(
            margin,
            margin + text_height + 8,
            page_width - margin,
            page_height - margin - 28,
        )
        page.draw_rect(image_rect, color=(0.72, 0.78, 0.84), width=0.8)
        page.insert_image(image_rect, stream=photo.image_bytes, keep_proportion=True, overlay=True)
        footer_rect = fitz.Rect(margin, page_height - 28, page_width - margin, page_height - 10)
        page.insert_textbox(
            footer_rect,
            f"Photo {idx} of {len(photos)}",
            fontname="helv",
            fontsize=8,
            color=(0.42, 0.47, 0.52),
            align=2,
        )

    if not photos:
        page = out.new_page(width=page_width, height=page_height)
        page.insert_textbox(
            fitz.Rect(50, 250, page_width - 50, 430),
            "No color photographs were detected in the uploaded PDF reports.",
            fontname="hebo",
            fontsize=15,
            color=(0.20, 0.25, 0.30),
            align=1,
        )

    return out.tobytes(garbage=4, deflate=True, clean=True)
