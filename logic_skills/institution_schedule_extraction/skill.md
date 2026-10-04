# Institution Schedule Extraction

Extract any data from institution PDFs (routines, schedules, syllabi, holidays, exam dates, etc.)

## Procedure

### 1. Find PDF links
- Scrape the institution's program/course details page
- Look for "Download Routine", "রুটিন", "Syllabus", "Schedule" or similar links
- PDFs are often split by branch, batch, step/phase

### 2. Download
- Use download_file.py: first pass ['url'] to list, second pass ['url', '1,2,3'] to download
- Save to a named folder e.g. D:/Ai/logic/<Institution>_<Year>/

### 3. Read PDFs
- Use fitz (PyMuPDF) — NOT pdfplumber (not available)
- import fitz; doc = fitz.open(path); text = page.get_text()
- Read all pages; print page numbers alongside text for orientation

### 4. Locate target data
- For specific info (holiday, exam, class): keyword scan across all pages
  - Bangla keywords: "বন্ধ", "ছুটি", "পূজা", "ঈদ", "পরীক্ষা", "ক্লাস"
  - English keywords: "off", "holiday", "exam", "class", "closed"
- For general routine extraction: read all pages sequentially, identify table structure from repeated date/day patterns
- Data is often embedded inline in schedule tables, not in separate sections

### 5. Date range → which PDF
- Schedules split by step/phase each covering a date range
- Check PDF header/first page for its coverage period
- Target the phase covering your date of interest

### 6. Act on extracted data
- Add to calendar: calendar_add_multiple_events.py
- Save summary to file if needed
- Color 11 (red) for holidays, default for classes/exams
