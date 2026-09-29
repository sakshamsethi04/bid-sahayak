"""Generates the fictional demo tender and bidder documents used by Demo Mode.

Run:  python -m app.demo.generate_demo_docs
The generated files are committed in app/demo/files, so this only needs to be
re-run if you change the scenario. Every document is fictional and watermarked.
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "files"
W, H = A4


def watermark(c):
    c.saveState()
    c.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.08))
    c.setFont("Helvetica-Bold", 60)
    c.translate(W / 2, H / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "DEMO DOCUMENT")
    c.restoreState()
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.grey)
    c.drawCentredString(W / 2, 12 * mm, "Fictional document generated for the BidSahayak SIH 2026 prototype demo. Not a real record.")


def para(c, x, y, text, size=10, leading=14, width=170 * mm, font="Helvetica"):
    """Very small word-wrapper. Returns the new y."""
    c.setFont(font, size)
    words, line = text.split(), ""
    for w in words:
        trial = (line + " " + w).strip()
        if c.stringWidth(trial, font, size) > width:
            c.drawString(x, y, line)
            y -= leading
            line = w
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def footer(c, page, total, label):
    watermark(c)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawRightString(W - 20 * mm, 18 * mm, f"{label}  |  Page {page} of {total}")


# ---------------------------------------------------------------- tender
def tender():
    c = canvas.Canvas(str(OUT / "Tender_GEM-2026-B-5873214.pdf"), pagesize=A4)
    total = 4
    # page 1
    c.setFillColor(colors.HexColor("#1F3864"))
    c.rect(0, H - 30 * mm, W, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, H - 17 * mm, "GeM Bid Document")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, H - 24 * mm, "Government e-Marketplace  |  Bid Document (DEMO)")
    c.setFillColor(colors.black)
    rows = [
        ("Bid Number", "GEM/2026/B/5873214"),
        ("Dated", "14-09-2026"),
        ("Bid End Date/Time", "20-10-2026 15:00:00"),
        ("Ministry", "Ministry of Petroleum and Natural Gas"),
        ("Organisation", "Demo Refinery Procurement Cell (fictional buyer)"),
        ("Item Category", "Supply, Installation and Commissioning of Industrial Centrifugal Pumps"),
        ("Total Quantity", "24"),
        ("Estimated Bid Value", "Rs. 4.8 Crore"),
        ("EMD Amount", "Rs. 2,40,000"),
        ("Type of Bid", "Two Packet Bid"),
    ]
    y = H - 45 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Bid Details")
    y -= 9 * mm
    for k, v in rows:
        c.setStrokeColor(colors.HexColor("#BBBBBB"))
        c.rect(20 * mm, y - 3 * mm, 60 * mm, 9 * mm)
        c.rect(80 * mm, y - 3 * mm, 110 * mm, 9 * mm)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(22 * mm, y, k)
        c.setFont("Helvetica", 9)
        c.drawString(82 * mm, y, v)
        y -= 9 * mm
    y -= 6 * mm
    y = para(c, 20 * mm, y, "Bidders are advised to read the eligibility and qualification criteria in Section 4 carefully. "
             "Bids not meeting the mandatory criteria are liable to be rejected after technical evaluation by the procurement officer.")
    footer(c, 1, total, "GEM/2026/B/5873214")
    c.showPage()

    # page 2
    y = H - 25 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, y, "Section 4: Eligibility and Qualification Criteria")
    y -= 10 * mm
    clauses = [
        ("4.1", "GST Registration: The bidder must possess a valid GST registration. The GSTIN and GST registration certificate (Form GST REG-06) shall be submitted with the bid."),
        ("4.2", "PAN: The bidder must submit a copy of the PAN card issued by the Income Tax Department in the name of the bidding entity."),
        ("4.3", "Udyam / MSME: Micro and Small Enterprises seeking purchase preference and EMD exemption must submit a valid Udyam Registration Certificate."),
        ("4.4", "Financial Capacity: Minimum average annual turnover of the bidder during the last three financial years shall be Rs. 10 Crore. Audited financial statements or a CA certificate for all three years shall be submitted."),
        ("4.5", "OEM Authorisation: Bidders who are not the Original Equipment Manufacturer must submit an OEM authorisation certificate for the offered product, valid for this bid."),
        ("4.6", "Make in India: Minimum local content shall be 50% as per the Public Procurement (Preference to Make in India) Order. A certificate from the statutory auditor or cost auditor shall be submitted."),
    ]
    for num, text in clauses:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, num)
        y = para(c, 32 * mm, y, text, width=158 * mm) - 5
    footer(c, 2, total, "GEM/2026/B/5873214")
    c.showPage()

    # page 3
    y = H - 25 * mm
    clauses = [
        ("4.7", "Validity of Documents: All certificates and registrations submitted must be valid as on the bid end date."),
        ("4.8", "Blacklisting / Debarment: The bidder shall not be blacklisted or debarred by any Ministry, Department or PSU of the Government of India. A self-declaration shall be submitted."),
    ]
    for num, text in clauses:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, num)
        y = para(c, 32 * mm, y, text, width=158 * mm) - 5
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, y, "Section 5: Special Conditions")
    y -= 10 * mm
    for num, text in [
        ("5.1", "Delivery and commissioning shall be completed within 90 days from the date of contract."),
        ("5.2", "Performance security of 5% of contract value shall be submitted within 15 days of award."),
        ("5.3", "Warranty: 24 months from the date of commissioning."),
        ("5.4", "Buyer may seek clarification from bidders on submitted documents during technical evaluation."),
    ]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, num)
        y = para(c, 32 * mm, y, text, width=158 * mm) - 5
    footer(c, 3, total, "GEM/2026/B/5873214")
    c.showPage()

    # page 4
    y = H - 25 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, y, "Section 6: Technical Specifications (summary)")
    y -= 10 * mm
    for line in ["Pump type: Horizontal end-suction centrifugal, API 610 compliant",
                 "Flow rate: 120 m3/h at 60 m head", "Motor: 45 kW, IE3 efficiency class",
                 "Material of construction: SS316 impeller and casing"]:
        y = para(c, 20 * mm, y, "- " + line)
    footer(c, 4, total, "GEM/2026/B/5873214")
    c.save()


# ---------------------------------------------------------------- bidder docs
def letterhead(c):
    c.setFillColor(colors.HexColor("#0B4F6C"))
    c.rect(0, H - 22 * mm, W, 22 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, H - 13 * mm, "ABC Engineering Pvt. Ltd.")
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, H - 18 * mm, "Registered Office: Plot 42, Okhla Industrial Area Phase II, New Delhi - 110020  |  CIN U29120DL2011PTC215874")
    c.setFillColor(colors.black)


def cover_letter():
    c = canvas.Canvas(str(OUT / "bidder" / "Bid_Cover_Letter.pdf"), pagesize=A4)
    letterhead(c)
    y = H - 35 * mm
    c.setFont("Helvetica", 10)
    for line in ["Date: 16-10-2026", "", "To,", "The Procurement Officer", "Demo Refinery Procurement Cell",
                 "", "Subject: Submission of bid against GEM/2026/B/5873214 - Industrial Centrifugal Pumps"]:
        c.drawString(20 * mm, y, line)
        y -= 6 * mm
    y -= 3 * mm
    y = para(c, 20 * mm, y, "Dear Sir/Madam, We, ABC Engineering Pvt. Ltd., having our registered office at Plot 42, Okhla Industrial Area Phase II, "
             "New Delhi, hereby submit our bid for the above tender. We are authorised dealers of Aqualine Pumps Ltd. for the offered model AQ-610.")
    y -= 3 * mm
    y = para(c, 20 * mm, y, "Declaration: We hereby declare that our firm has not been blacklisted or debarred by any Ministry, Department or PSU of the Government of India as on date.", font="Helvetica-Bold")
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Enclosures:")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    for e in ["1. GST Registration Certificate (Form GST REG-06)", "2. PAN Card", "3. Udyam Registration Certificate",
              "4. Audited Financial Statements FY 2025-26", "5. OEM Authorisation Certificate from Aqualine Pumps Ltd. (Annexure-5)",
              "6. Local Content Certificate"]:
        c.drawString(25 * mm, y, e)
        y -= 6 * mm
    y -= 12 * mm
    c.drawString(20 * mm, y, "For ABC Engineering Pvt. Ltd.")
    c.drawString(20 * mm, y - 18 * mm, "Rajesh Kumar, Director")
    footer(c, 1, 1, "ABC Engineering Pvt. Ltd.")
    c.save()


def gst():
    c = canvas.Canvas(str(OUT / "bidder" / "GST_Certificate.pdf"), pagesize=A4)
    y = H - 25 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W / 2, y, "Government of India")
    c.drawCentredString(W / 2, y - 6 * mm, "Form GST REG-06")
    c.drawCentredString(W / 2, y - 12 * mm, "Registration Certificate")
    y -= 25 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "Registration Number: 27AABCA1234F1Z5")
    y -= 10 * mm
    for k, v in [("1. Legal Name", "ABC ENGINEERING PRIVATE LIMITED"), ("2. Trade Name, if any", "ABC ENGINEERING"),
                 ("3. Constitution of Business", "Private Limited Company"), ("4. Address of Principal Place of Business", "See Annexure A"),
                 ("5. Date of Liability", "01/07/2017"), ("6. Period of Validity", "From 01/07/2017 To Not Applicable"),
                 ("7. Type of Registration", "Regular"), ("8. Particulars of Approving Authority", "Centre, Mumbai Zone")]:
        c.drawString(20 * mm, y, k)
        c.drawString(105 * mm, y, v)
        y -= 8 * mm
    footer(c, 1, 3, "Form GST REG-06")
    c.showPage()
    y = H - 25 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Annexure A")
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "GSTIN: 27AABCA1234F1Z5")
    y -= 8 * mm
    c.drawString(20 * mm, y, "Legal Name: ABC ENGINEERING PRIVATE LIMITED")
    y -= 12 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Details of Principal Place of Business")
    y -= 8 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, "Principal Place of Business: Unit 7, Marol Industrial Estate, Andheri East, Mumbai, Maharashtra, 400093")
    y -= 8 * mm
    c.drawString(20 * mm, y, "Nature of Business Activity: Supplier of Services, Wholesale Business")
    footer(c, 2, 3, "Form GST REG-06")
    c.showPage()
    y = H - 25 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Annexure B - Details of Managing / Authorized Partners")
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    for line in ["1. Rajesh Kumar - Director", "2. Anita Sharma - Director"]:
        c.drawString(20 * mm, y, line)
        y -= 8 * mm
    footer(c, 3, 3, "Form GST REG-06")
    c.save()


def pan():
    c = canvas.Canvas(str(OUT / "bidder" / "PAN_Card.pdf"), pagesize=A4)
    x, y = 30 * mm, H - 110 * mm
    c.setFillColor(colors.HexColor("#E8F1FB"))
    c.roundRect(x, y, 150 * mm, 80 * mm, 6 * mm, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x + 8 * mm, y + 68 * mm, "INCOME TAX DEPARTMENT        GOVT. OF INDIA")
    c.setFont("Helvetica", 10)
    c.drawString(x + 8 * mm, y + 52 * mm, "Name: ABC ENGINEERING PRIVATE LIMITED")
    c.drawString(x + 8 * mm, y + 42 * mm, "Date of Incorporation/Formation: 12/03/2011")
    c.drawString(x + 8 * mm, y + 28 * mm, "Permanent Account Number")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x + 8 * mm, y + 18 * mm, "AABCA1234F")
    footer(c, 1, 1, "PAN Card (copy)")
    c.save()


def udyam_scan():
    """A scanned image (no text layer) so the OCR path runs for real."""
    img = Image.new("RGB", (1654, 2339), (250, 249, 244))
    d = ImageDraw.Draw(img)
    try:
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
        reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
    except OSError:
        bold = reg = small = ImageFont.load_default()
    d.rectangle([60, 60, 1594, 2279], outline=(40, 60, 120), width=6)
    d.text((827, 180), "GOVERNMENT OF INDIA", font=bold, fill=(20, 20, 20), anchor="mm")
    d.text((827, 250), "MINISTRY OF MICRO, SMALL AND MEDIUM ENTERPRISES", font=reg, fill=(20, 20, 20), anchor="mm")
    d.text((827, 360), "UDYAM REGISTRATION CERTIFICATE", font=bold, fill=(20, 30, 90), anchor="mm")
    rows = [("UDYAM REGISTRATION NUMBER", "UDYAM-MH-19-0045821"),
            ("NAME OF ENTERPRISE", "ABC ENGINEERING PRIVATE LIMITED"),
            ("TYPE OF ENTERPRISE", "Small"),
            ("MAJOR ACTIVITY", "Manufacturing"),
            ("SOCIAL CATEGORY", "General"),
            ("DATE OF INCORPORATION", "12/03/2011"),
            ("DATE OF UDYAM REGISTRATION", "22/08/2020")]
    y = 520
    for k, v in rows:
        d.text((140, y), k, font=reg, fill=(30, 30, 30))
        d.text((140, y + 55), v, font=bold, fill=(10, 10, 10))
        y += 170
    d.text((140, 1850), "Disclaimer: This is a DEMO certificate generated for the BidSahayak prototype.", font=small, fill=(120, 40, 40))
    img = img.rotate(0.6, expand=False, fillcolor=(250, 249, 244))
    rnd = random.Random(7)
    px = img.load()
    for _ in range(9000):
        x, yy = rnd.randrange(img.width), rnd.randrange(img.height)
        g = rnd.randrange(170, 230)
        px[x, yy] = (g, g, g)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img.save(OUT / "bidder" / "Udyam_Certificate_scan.png")


def financials():
    c = canvas.Canvas(str(OUT / "bidder" / "Financial_Statement_FY2025-26.pdf"), pagesize=A4)
    total = 14
    titles = {1: "Annual Report FY 2025-26", 2: "Corporate Information", 3: "Directors' Report", 4: "Directors' Report (contd.)",
              5: "Management Discussion and Analysis", 6: "Independent Auditor's Report", 7: "Independent Auditor's Report (contd.)",
              8: "Annexure to Auditor's Report", 9: "Significant Accounting Policies", 10: "Balance Sheet as at 31 March 2026",
              11: "Notes to Balance Sheet", 12: "Statement of Profit and Loss for the year ended 31 March 2026",
              13: "Cash Flow Statement", 14: "Notes to Accounts"}
    for p in range(1, total + 1):
        letterhead(c)
        y = H - 35 * mm
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, y, titles[p])
        y -= 12 * mm
        if p == 12:
            c.setFont("Helvetica", 9)
            c.drawString(20 * mm, y, "(All amounts in Rs.)")
            c.drawString(120 * mm, y, "FY 2025-26")
            c.drawString(160 * mm, y, "FY 2024-25")
            y -= 9 * mm
            for k, a, b in [("Revenue from Operations", "8,70,42,615", "9,64,10,220"), ("Other Income", "12,40,300", "9,85,110"),
                            ("Total Income", "8,82,82,915", "9,73,95,330"), ("Cost of Materials Consumed", "5,62,18,400", "6,21,77,050"),
                            ("Employee Benefit Expenses", "1,08,55,000", "1,02,40,000"), ("Finance Costs", "18,20,450", "21,05,300"),
                            ("Depreciation", "24,10,000", "22,80,000"), ("Other Expenses", "92,64,120", "98,12,600"),
                            ("Profit Before Tax", "77,14,945", "1,07,80,380"), ("Tax Expense", "19,41,000", "27,13,000"),
                            ("Profit for the Year", "57,73,945", "80,67,380")]:
                c.setFont("Helvetica-Bold" if k.startswith(("Revenue", "Total", "Profit for")) else "Helvetica", 9)
                c.drawString(20 * mm, y, k)
                c.drawRightString(145 * mm, y, a)
                c.drawRightString(185 * mm, y, b)
                y -= 7 * mm
            y -= 8 * mm
            c.setFont("Helvetica", 8)
            c.drawString(20 * mm, y, "For S. Mehta & Associates, Chartered Accountants, FRN 118245W  |  UDIN 26114532BGXKLM7788")
        elif p == 1:
            c.setFont("Helvetica", 11)
            c.drawString(20 * mm, y, "ABC Engineering Pvt. Ltd.  |  CIN U29120DL2011PTC215874")
            c.drawString(20 * mm, y - 8 * mm, "Audited financial statements for the financial year ended 31 March 2026")
        else:
            rnd = random.Random(p)
            filler = ("The Company continued to focus on industrial pumping solutions for refinery, water and process industries. "
                      "Figures are presented in accordance with Schedule III of the Companies Act, 2013. ")
            for _ in range(rnd.randint(4, 7)):
                y = para(c, 20 * mm, y, filler * 2, size=9, leading=12) - 6
        footer(c, p, total, "Annual Report FY 2025-26")
        c.showPage()
    c.save()


def local_content():
    c = canvas.Canvas(str(OUT / "bidder" / "Local_Content_Certificate.pdf"), pagesize=A4)
    y = H - 30 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, y, "Certificate of Local Content")
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, y - 6 * mm, "(Public Procurement - Preference to Make in India Order, 2017, as amended)")
    y -= 22 * mm
    y = para(c, 20 * mm, y, "This is to certify that the item 'Industrial Centrifugal Pump, Model AQ-610' offered by ABC Engineering Pvt. Ltd. "
             "against Bid No. GEM/2026/B/5873214 has a local content of 62% as computed in accordance with the above Order.")
    y -= 6 * mm
    for k, v in [("Local Content", "62%"), ("Class of Supplier", "Class-I local supplier"), ("Date of Issue", "02/09/2026"),
                 ("Valid Up To", "31/03/2027"), ("Issued by", "S. Mehta & Associates, Chartered Accountants (Statutory Auditor)"),
                 ("UDIN", "26114532BGXKLM9921")]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, k + ":")
        c.setFont("Helvetica", 10)
        c.drawString(65 * mm, y, v)
        y -= 8 * mm
    footer(c, 1, 1, "Local Content Certificate")
    c.save()


if __name__ == "__main__":
    (OUT / "bidder").mkdir(parents=True, exist_ok=True)
    tender(); cover_letter(); gst(); pan(); udyam_scan(); financials(); local_content()
    print("Demo documents written to", OUT)
