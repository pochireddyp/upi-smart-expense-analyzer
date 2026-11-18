"""Synthetic CSV bank statement generator for UPI Smart Expense Analyzer testing.

Generates realistic mock CSV bank statements strictly for automated testing.
Contains ZERO real personal or financial data.
"""

from pathlib import Path


def create_hdfc_sample_csv(destination: Path) -> Path:
    """Create a synthetic HDFC bank statement CSV with 15 valid transaction rows.

    Args:
        destination: Path where the CSV file should be created.

    Returns:
        Path: The created CSV file path.
    """
    content = (
        "Date,Narration,Chq/Ref No,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "01/01/2026,NEFT/CMS/SALARY/JAN2026/TECHCORP,000921029381,01/01/2026,,95000.00,124500.00\n"
        "03/01/2026,UPI/401029381/SWIGGY/PAYTM,321873129012,03/01/2026,485.00,,124015.00\n"
        "04/01/2026,UPI/402910382/ZEPTO/INSTANT,323910294821,04/01/2026,620.00,,123395.00\n"
        "05/01/2026,UPI/401029381/NETFLIX/MANDATE,401029381928,05/01/2026,649.00,,122746.00\n"
        "07/01/2026,UPI/404910294/AIRTEL/BILL,404910294821,07/01/2026,1179.00,,121567.00\n"
        "10/01/2026,UPI/405910285/BESCOM/PORTAL,405910285921,10/01/2026,1850.00,,119717.00\n"
        "12/01/2026,UPI/402910382/SPOTIFY/RECURRING,402910382918,12/01/2026,119.00,,119598.00\n"
        "15/01/2026,UPI/32681029/UBER/PAYTM,326810294812,15/01/2026,340.00,,119258.00\n"
        "18/01/2026,UPI/33081029/AMAZONPAY/ICICI,330810294812,18/01/2026,1650.00,,117608.00\n"
        "20/01/2026,UPI/33181029/MYNTRA/RETAIL,331810294812,20/01/2026,2499.00,,115109.00\n"
        "22/01/2026,UPI/408910298/GIFT/PHONEPE,408910298129,22/01/2026,1500.00,,113609.00\n"
        "25/01/2026,UPI/32481029/BLINKIT/ICICI,324810294819,25/01/2026,890.00,,112719.00\n"
        "28/01/2026,UPI/32189401/ZOMATO/AXIS,321894019281,28/01/2026,340.00,,112379.00\n"
        "30/01/2026,UPI/32201928/CHAIPOINT/HDFC,322019284918,30/01/2026,85.00,,112294.00\n"
        "31/01/2026,UPI/32981029/SHELL/FUEL,329810294810,31/01/2026,1200.00,,111094.00\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def create_sbi_sample_csv(destination: Path) -> Path:
    """Create a synthetic SBI bank statement CSV with 8 preamble lines and 10 transactions.

    Args:
        destination: Path where the CSV file should be created.

    Returns:
        Path: The created CSV file path.
    """
    content = (
        "Account Name : Mr. Sample Citizen\n"
        "Address : 42 Green Park Residency, Bengaluru 560038\n"
        "Account Number : 0000003291029381\n"
        "Branch : INDIRANAGAR BANGALORE\n"
        "Drawing Power : 0.00\n"
        "Interest Rate : 2.70 % p.a.\n"
        "MOD Balance : 0.00\n"
        "CIF No : 829102938\n"
        "Txn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance\n"
        "01-Jan-2026,01-Jan-2026,CREDIT-INTEREST EARNED,TRANSFER-102938,,420.00,84520.00\n"
        "02-Jan-2026,02-Jan-2026,UPI/32291028/CHAI/PAYTMQR,UPI-322910284918,30.00,,84490.00\n"
        "04-Jan-2026,04-Jan-2026,UPI/32781029/OLACABS/HDFC,UPI-327810294819,280.00,,84210.00\n"
        "08-Jan-2026,08-Jan-2026,UPI/32881029/METRO/SMARTCARD,UPI-328810294810,100.00,,84110.00\n"
        "11-Jan-2026,11-Jan-2026,UPI/33281029/APOLLO/MEDICAL,UPI-332810294812,420.00,,83690.00\n"
        "14-Jan-2026,14-Jan-2026,UPI/403910283/HOTSTAR/SUB,UPI-403910283918,430.00,,83260.00\n"
        "17-Jan-2026,17-Jan-2026,UPI/32581028/NATURESBASKET/POS,UPI-325810284910,1450.00,,81810.00\n"
        "20-Jan-2026,20-Jan-2026,REVERSAL/UPI/32189401/REFUND,UPI-REFUND-901829,,340.00,82150.00\n"
        "24-Jan-2026,24-Jan-2026,UPI/407910297/SPLIT/PAYTM,UPI-407910297481,,1250.00,83400.00\n"
        "29-Jan-2026,29-Jan-2026,UPI/406910296/RENT/TRANSFER,UPI-406910296129,22000.00,,61400.00\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination
