"""P2 stage 6: certify corrections in auto-ontology, one round at a time.

Usage: python -I corrections.py R1|R2|R3
Each call is logged to corrections_log.jsonl. No correction names a holdout company
(Amazon, Exxon Mobil, Berkshire Hathaway); examples use Alphabet, Coca-Cola and Pfizer.
"""
import json, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
API = "http://localhost:3001"
HDR = {"Content-Type": "application/json", "x-auto-ontology-user-id": "216bca1f-6796-4841-aebf-fc7846fe31f2"}
LOG = HERE / "corrections_log.jsonl"

TERM_NUM, TERM_PRE, TERM_SUB, TERM_TAG = ("6d64d32e-570f-46de-a952-1cc2990fc09c", "554a32d1-9e16-4fb6-941b-46fd72efa1b6",
                                          "19d29acf-75f2-426b-a6b1-80de0e90860c", "bed407b3-3421-4004-af82-535e20b733a5")
JOIN_RULE = ("Join num to sub on num.adsh = sub.adsh (the filing). Join num to tag on BOTH num.tag = tag.tag "
             "AND num.version = tag.version. Never join num to pre or num to tag on tag alone.")


def call(method, path, body=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None, HDR, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            status, text = r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode()[:300]
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "round": sys.argv[1], "method": method,
                            "path": path, "body": body, "status": status, "response": text}) + "\n")
    print(status, method, path)
    return status


def r1():
    """Certified names and descriptions for terms and the columns behind the wrong answers."""
    terms = {
        TERM_NUM: ("Reported Financial Fact",
                   "One numeric fact from an SEC filing (table num): the value of one XBRL tag (num.tag) for one period "
                   "(num.ddate, num.qtrs) in one filing (num.adsh). Revenue, net income and total assets are rows of this "
                   "table, selected by num.tag: revenue = 'Revenues', else 'RevenueFromContractWithCustomerExcludingAssessedTax', "
                   "else 'RevenuesNetOfInterestExpense' (banks); net income = 'NetIncomeLoss', else "
                   "'NetIncomeLossAvailableToCommonStockholdersBasic'; total assets = 'Assets'. A company total is ONE row: "
                   "never SUM num.value across tags or filings. " + JOIN_RULE),
        TERM_PRE: ("Statement Presentation Line",
                   "One line of a financial statement as the filer presented it (table pre): statement type stmt "
                   "(IS income statement, BS balance sheet, CF cash flow), line order and the filer's own label plabel. "
                   "Labels differ by company, so do not filter amounts by plabel; select amounts in num by num.tag."),
        TERM_SUB: ("SEC Filing Submission",
                   "One SEC filing (table sub), one row per accession number adsh, with the filer's name, CIK, form type "
                   "(form = '10-K' for an annual report), fiscal year end and period (the balance sheet date)."),
    }
    for tid, (name, desc) in terms.items():
        call("PATCH", f"/api/terms/{tid}", {"name": name, "description": desc, "name_certified": True, "description_certified": True})
    attrs = {
        (TERM_NUM, "e0371b1d-3cbd-4ff7-ba77-bcb285ce18ed"): ("Duration In Quarters",
            "num.qtrs: how many quarters the value covers. 4 = one full fiscal year (use for annual income statement "
            "amounts: revenue, net income). 0 = a point in time (use for balance sheet amounts: total assets). 1 = one quarter."),
        (TERM_NUM, "a61306bb-be52-47d9-9e9d-03dfb328ae0b"): ("Reporting Segments",
            "num.segments: NULL for the consolidated company total. A non-null value is a breakdown (segment, product, "
            "geography). For a company total, filter num.segments IS NULL."),
        (TERM_NUM, "64d0dbe7-44fc-44e6-bc47-0f870347de43"): ("Coregistrant",
            "num.coreg: NULL for the filing company itself. A non-null value is a co-registrant subsidiary. For a "
            "company total, filter num.coreg IS NULL."),
        (TERM_NUM, "76763bcf-d8f9-4698-84a7-b66d78212b31"): ("Period End Date",
            "num.ddate: end date of the period the value covers. For a fiscal-year amount it equals the fiscal year end, "
            "which is sub.period of the 10-K (for example 2025-12-31, or 2026-01-31 for a January year end)."),
        (TERM_NUM, "f29b02c5-465b-48e7-bbda-792b8c5acd73"): ("Reported Value",
            "num.value: the reported amount in the unit num.uom. For uom = 'USD' it is in whole US dollars, not thousands "
            "or millions."),
        (TERM_SUB, "61c93eba-95e4-43a2-944b-3dd1fa9a355c"): ("Company Name",
            "sub.name: the filer's name as registered with the SEC, in upper case, for example 'ALPHABET INC.', "
            "'COCA COLA CO', 'PFIZER INC', 'JPMORGAN CHASE & CO'. Match with ILIKE on the distinctive word, and choose "
            "the parent company, not a finance subsidiary such as 'CATERPILLAR FINANCIAL SERVICES CORP'."),
        (TERM_SUB, "cfae7ef9-15f6-4eaa-a866-9c4c53e4b87c"): ("Filing Form Type",
            "sub.form: the SEC form. '10-K' is the annual report that holds fiscal-year revenue, net income and total assets."),
        (TERM_SUB, "25df601a-ae1b-4955-a0c1-b68a6b9e15d8"): ("Accession Number",
            "sub.adsh: the accession number, the unique ID of one filing (format 0001652044-26-000018). num.adsh and "
            "pre.adsh refer to it."),
        (TERM_SUB, "2521266e-88b2-4ce0-9bce-85bacee7a772"): ("Balance Sheet Date",
            "sub.period: the balance sheet date of the filing, which for a 10-K is the fiscal year end. Use num.ddate = sub.period."),
    }
    for (tid, aid), (name, desc) in attrs.items():
        call("PATCH", f"/api/terms/{tid}/column-attributes/{aid}", {"name": name, "description": desc, "certified": True})


METRICS = {
    "revenue": ("('Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','RevenuesNetOfInterestExpense')",
                "CASE n.tag WHEN 'Revenues' THEN 1 WHEN 'RevenueFromContractWithCustomerExcludingAssessedTax' THEN 2 ELSE 3 END", 4),
    "net_income": ("('NetIncomeLoss','NetIncomeLossAvailableToCommonStockholdersBasic')",
                   "CASE n.tag WHEN 'NetIncomeLoss' THEN 1 ELSE 2 END", 4),
    "total_assets": ("('Assets')", "1", 0),
}


def metric_sql(metric, company, period):
    tags, prio, qtrs = METRICS[metric]
    return (f"SELECT n.value AS {metric} FROM sec.public.num AS n JOIN sec.public.sub AS s ON s.adsh = n.adsh "
            f"WHERE s.name = '{company}' AND s.form = '10-K' AND s.period = '{period}' AND n.tag IN {tags} "
            f"AND n.ddate = s.period AND n.qtrs = {qtrs} AND n.segments IS NULL AND n.coreg IS NULL AND n.uom = 'USD' "
            f"ORDER BY {prio} LIMIT 1")


def r2():
    """Certified SQL attributes under the num term: one per metric, as a reusable definition."""
    desc = {
        "revenue": "Total revenue of a company for a fiscal year, from its 10-K: one row of num, tag by priority "
                   "Revenues > RevenueFromContractWithCustomerExcludingAssessedTax > RevenuesNetOfInterestExpense, qtrs = 4, "
                   "consolidated (segments and coreg NULL). Replace the company name and period.",
        "net_income": "Net income attributable to the company for a fiscal year, from its 10-K: tag NetIncomeLoss, else "
                      "NetIncomeLossAvailableToCommonStockholdersBasic, qtrs = 4, consolidated. Replace the company name and period.",
        "total_assets": "Total assets at the fiscal year end, from the 10-K balance sheet: tag Assets, qtrs = 0, "
                        "consolidated. Replace the company name and period.",
    }
    names = {"revenue": "Fiscal Year Revenue", "net_income": "Fiscal Year Net Income", "total_assets": "Year End Total Assets"}
    for m in METRICS:
        call("POST", "/api/sql-attributes", {"name": names[m], "description": desc[m],
                                             "expression": metric_sql(m, "ALPHABET INC.", "2025-12-31"), "term_id": TERM_NUM})


def r3():
    """Verified SQL examples (custom analyses), for non-holdout companies only."""
    ex = [("revenue", "COCA COLA CO", "2025-12-31", "What was Coca-Cola's total revenue for the fiscal year ended December 31, 2025?"),
          ("net_income", "PFIZER INC", "2025-12-31", "What was Pfizer's net income for the fiscal year ended December 31, 2025?"),
          ("total_assets", "ALPHABET INC.", "2025-12-31", "What were Alphabet's total assets as of December 31, 2025?")]
    for m, co, per, q in ex:
        call("POST", "/api/custom-analyses", {"name": q, "description": f"Verified pattern for {m.replace('_', ' ')} from a 10-K. "
                                              "Change the company name (sub.name) and the period (sub.period) for another company or year.",
                                              "sql": metric_sql(m, co, per)})


if __name__ == "__main__":
    {"R1": r1, "R2": r2, "R3": r3}[sys.argv[1]]()
