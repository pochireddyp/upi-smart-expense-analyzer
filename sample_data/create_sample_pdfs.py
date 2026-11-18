"""Script to generate realistic synthetic bank PDF statements for testing.

Generates:
1. sample_hdfc_statement.pdf (Multi-page digital PDF with table lines and transactions)
2. sample_locked_statement.pdf (Encrypted PDF protected with 'password123')
3. sample_scanned_stub.pdf (Text-less PDF to test scanned document detection)
"""

from pathlib import Path
from typing import Optional
import pymupdf

OUTPUT_DIR = Path(__file__).resolve().parent


def create_hdfc_sample_pdf(destination: Optional[Path] = None) -> Path:
    """Create a multi-page synthetic HDFC bank statement PDF with vector table lines."""
    pdf_path = destination if destination is not None else OUTPUT_DIR / "sample_hdfc_statement.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()

    # --- Page 1 ---
    page1 = doc.new_page(width=595, height=842)  # A4 size

    # Header & Preamble
    page1.insert_text((50, 45), "HDFC BANK LIMITED", fontsize=14, fontname="helv", color=(0.05, 0.2, 0.6))
    page1.insert_text((50, 65), "Account Statement: 01/01/2026 to 31/01/2026", fontsize=10, fontname="helv")
    page1.insert_text((50, 80), "Customer Name: Sample User | Account: 0000003291029381", fontsize=9, fontname="helv")

    headers = ["Date", "Narration", "Chq/Ref No", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
    col_x = [50, 110, 290, 370, 450, 530]

    # Draw Table Header
    y = 110
    page1.draw_rect(pymupdf.Rect(45, y - 12, 545, y + 6), color=(0.85, 0.9, 0.95), fill=(0.85, 0.9, 0.95))
    for i, h in enumerate(headers):
        page1.insert_text((col_x[i], y), h, fontsize=8, fontname="helv")
    page1.draw_line((45, y + 6), (545, y + 6), color=(0.4, 0.4, 0.4))

    # Page 1 Rows
    rows_p1 = [
        ["01/01/2026", "NEFT/CMS/SALARY/JAN2026/TECHCORP", "000921029381", "", "95000.00", "124500.00"],
        ["03/01/2026", "UPI/401029381/SWIGGY/PAYTM", "321873129012", "485.00", "", "124015.00"],
        ["04/01/2026", "UPI/402910382/ZEPTO/INSTANT", "323910294821", "620.00", "", "123395.00"],
        ["05/01/2026", "UPI/401029381/NETFLIX/MANDATE", "401029381928", "649.00", "", "122746.00"],
        ["07/01/2026", "UPI/404910294/AIRTEL/BILL", "404910294821", "1179.00", "", "121567.00"],
        ["10/01/2026", "UPI/405910285/BESCOM/PORTAL", "405910285921", "1850.00", "", "119717.00"],
        ["12/01/2026", "UPI/402910382/SPOTIFY/RECURRING", "402910382918", "119.00", "", "119598.00"],
        ["15/01/2026", "UPI/32681029/UBER/PAYTM", "326810294812", "340.00", "", "119258.00"],
    ]

    for row in rows_p1:
        y += 24
        for i, val in enumerate(row):
            page1.insert_text((col_x[i], y), val, fontsize=8, fontname="helv")
        page1.draw_line((45, y + 4), (545, y + 4), color=(0.8, 0.8, 0.8))

    page1.insert_text((270, 800), "Page 1 of 2", fontsize=8, fontname="helv")

    # --- Page 2 ---
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 45), "HDFC BANK LIMITED (Continued)", fontsize=12, fontname="helv", color=(0.05, 0.2, 0.6))

    y = 80
    page2.draw_rect(pymupdf.Rect(45, y - 12, 545, y + 6), color=(0.85, 0.9, 0.95), fill=(0.85, 0.9, 0.95))
    for i, h in enumerate(headers):
        page2.insert_text((col_x[i], y), h, fontsize=8, fontname="helv")
    page2.draw_line((45, y + 6), (545, y + 6), color=(0.4, 0.4, 0.4))

    rows_p2 = [
        ["18/01/2026", "UPI/33081029/AMAZONPAY/ICICI", "330810294812", "1650.00", "", "117608.00"],
        ["20/01/2026", "UPI/33181029/MYNTRA/RETAIL", "331810294812", "2499.00", "", "115109.00"],
        ["22/01/2026", "UPI/408910298/GIFT/PHONEPE", "408910298129", "1500.00", "", "113609.00"],
        ["25/01/2026", "UPI/32481029/BLINKIT/ICICI", "324810294819", "890.00", "", "112719.00"],
        ["28/01/2026", "UPI/32189401/ZOMATO/AXIS", "321894019281", "340.00", "", "112379.00"],
        ["30/01/2026", "UPI/32201928/CHAIPOINT/HDFC", "322019284918", "85.00", "", "112294.00"],
        ["31/01/2026", "UPI/32981029/SHELL/FUEL", "329810294810", "1200.00", "", "111094.00"],
    ]

    for row in rows_p2:
        y += 24
        for i, val in enumerate(row):
            page2.insert_text((col_x[i], y), val, fontsize=8, fontname="helv")
        page2.draw_line((45, y + 4), (545, y + 4), color=(0.8, 0.8, 0.8))

    page2.insert_text((270, 800), "Page 2 of 2", fontsize=8, fontname="helv")

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def create_locked_sample_pdf(destination: Optional[Path] = None, password: str = "password123") -> Path:
    """Create a synthetic password-encrypted bank PDF statement."""
    pdf_path = destination if destination is not None else OUTPUT_DIR / "sample_locked_statement.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    page.insert_text((50, 50), "STATE BANK OF INDIA - CONFIDENTIAL", fontsize=12, fontname="helv")
    page.insert_text((50, 70), "Encrypted Statement: Jan 2026", fontsize=10, fontname="helv")

    headers = ["Txn Date", "Narration", "Debit", "Credit", "Balance"]
    col_x = [50, 130, 330, 410, 490]
    y = 100

    for i, h in enumerate(headers):
        page.insert_text((col_x[i], y), h, fontsize=9, fontname="helv")

    rows = [
        ["02/01/2026", "UPI/32291028/CHAI/PAYTMQR", "30.00", "", "84490.00"],
        ["04/01/2026", "UPI/32781029/OLACABS/HDFC", "280.00", "", "84210.00"],
        ["10/01/2026", "SALARY CREDIT TECHCORP", "", "95000.00", "179210.00"],
        ["14/01/2026", "UPI/403910283/HOTSTAR/SUB", "430.00", "", "178780.00"],
    ]

    for r in rows:
        y += 24
        for i, val in enumerate(r):
            page.insert_text((col_x[i], y), val, fontsize=8, fontname="helv")

    # Save encrypted
    perm = int(
        pymupdf.PDF_PERM_ACCESSIBILITY
        | pymupdf.PDF_PERM_PRINT
        | pymupdf.PDF_PERM_COPY
        | pymupdf.PDF_PERM_ANNOTATE
    )
    doc.save(
        str(pdf_path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw=password,
        owner_pw="adminpass",
        permissions=perm,
    )
    doc.close()
    return pdf_path


def create_scanned_stub_pdf(destination: Optional[Path] = None) -> Path:
    """Create a text-less synthetic PDF simulating an image-only / scanned document."""
    pdf_path = destination if destination is not None else OUTPUT_DIR / "sample_scanned_stub.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    # Draw shapes only (no extractable text)
    page.draw_rect(pymupdf.Rect(50, 50, 500, 700), color=(0.5, 0.5, 0.5), width=2)
    page.draw_line((50, 100), (500, 100), color=(0.5, 0.5, 0.5))

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


if __name__ == "__main__":
    create_hdfc_sample_pdf()
    create_locked_sample_pdf()
    create_scanned_stub_pdf()
    print("Synthetic PDF fixtures created successfully.")
