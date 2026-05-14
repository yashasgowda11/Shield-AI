"""Generate three test contract PDFs targeting specific Shield AI decisions.

AUTO_APPROVE  → composite ≥ 82, critical=0, high≤1
MANAGER_REVIEW → composite 63-81, critical=0, high≤2
LEGAL_REVIEW  → composite 38-62 (or high≥3)

Strategy:
  AUTO_APPROVE  - all compliance clauses explicit, low-risk balanced terms
  MANAGER_REVIEW - critical compliance items present (no REJECT override),
                   2-3 High risk clauses, some medium compliance gaps
  LEGAL_REVIEW  - critical keywords present to avoid REJECT, many missing
                   compliance items, 4+ High risk findings
"""
from fpdf import FPDF
import pathlib

OUT_DIR = pathlib.Path(__file__).parent.parent / "test_contracts"
OUT_DIR.mkdir(exist_ok=True)


class ContractPDF(FPDF):
    def __init__(self, title: str):
        super().__init__()
        self._doc_title = title
        self.set_margins(25, 20, 25)
        self.set_auto_page_break(auto=True, margin=20)
        self.add_page()

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, self._doc_title, align="R")
        self.ln(2)
        self.set_draw_color(180, 180, 180)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    def _w(self):
        return self.w - self.l_margin - self.r_margin

    def h1(self, text):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(20, 20, 60)
        self.ln(4)
        self.multi_cell(self._w(), 7, text)
        self.ln(2)

    def h2(self, text):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(40, 40, 100)
        self.ln(3)
        self.multi_cell(self._w(), 6, text)
        self.ln(1)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self._w(), 5.5, text)
        self.ln(2)

    def clause(self, number, title, text):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(20, 20, 60)
        self.multi_cell(self._w(), 6, f"{number}. {title}")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(self._w(), 5.5, text)
        self.ln(2)

    def divider(self):
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)


# =============================================================================
# 1. AUTO_APPROVE - Comprehensive SaaS Data Processing Agreement
#    Target: composite ~90, risk ~8, compliance ~95%, quality ~100%
# =============================================================================

def make_auto_approve():
    pdf = ContractPDF("SHIELD-TEST-AUTO-APPROVE-SAAS-DPA-2024")
    pdf.h1("MASTER SAAS SUBSCRIPTION AND DATA PROCESSING AGREEMENT")

    pdf.body(
        "This Master SaaS Subscription and Data Processing Agreement (\"Agreement\") is entered "
        "into as of January 1, 2024 (\"Effective Date\") by and between:\n\n"
        "Vendor: SecureCloud Technologies Inc., a Delaware corporation with its principal place "
        "of business at 500 Innovation Drive, San Francisco, CA 94105 (\"Vendor\"); and\n\n"
        "Customer: HealthBridge Partners LLC, a New York limited liability company with its "
        "principal place of business at 200 Medical Plaza, New York, NY 10001 (\"Customer\").\n\n"
        "Collectively referred to as the \"Parties.\""
    )
    pdf.divider()

    pdf.h2("RECITALS")
    pdf.body(
        "WHEREAS, Vendor operates a cloud-based software platform for healthcare data management; "
        "and WHEREAS, Customer desires to subscribe to said platform and process certain Protected "
        "Health Information (PHI) and personal data thereon; NOW THEREFORE, in consideration of "
        "the mutual covenants herein, the Parties agree as follows:"
    )

    pdf.h2("ARTICLE 1 - TERM AND RENEWAL")
    pdf.clause("1.1", "Initial Term",
        "This Agreement commences on the Effective Date and continues for three (3) years "
        "unless earlier terminated in accordance with Article 12 (\"Initial Term\").")
    pdf.clause("1.2", "Renewal",
        "Upon expiration of the Initial Term, this Agreement shall automatically renew for "
        "successive one-year periods unless either Party provides written notice of non-renewal "
        "at least ninety (90) days prior to the end of the then-current term.")
    pdf.clause("1.3", "Payment Terms",
        "Customer shall pay all fees invoiced within thirty (30) days of invoice date. Fees are "
        "non-refundable except as expressly set forth herein. Vendor may adjust fees upon "
        "sixty (60) days written notice, applicable only to renewal terms.")

    pdf.h2("ARTICLE 2 - SERVICES AND OBLIGATIONS")
    pdf.clause("2.1", "Services",
        "Vendor shall provide the software services described in Schedule A (\"Services\") with "
        "commercially reasonable skill and care. Vendor warrants the Services will perform "
        "materially in accordance with the documentation.")
    pdf.clause("2.2", "Customer Obligations",
        "Customer shall: (a) provide accurate information; (b) designate an authorized contact; "
        "(c) comply with applicable law; (d) maintain confidentiality of access credentials; "
        "(e) promptly report any suspected security incidents to Vendor.")
    pdf.clause("2.3", "Uptime SLA",
        "Vendor commits to 99.9% monthly uptime. In the event of SLA breach, Customer is "
        "entitled to service credits as detailed in Schedule B. Both Parties acknowledge this "
        "as the exclusive remedy for downtime.")

    pdf.h2("ARTICLE 3 - BUSINESS ASSOCIATE AGREEMENT (BAA)")
    pdf.clause("3.1", "BAA Incorporation",
        "This Article constitutes a Business Associate Agreement as required under the Health "
        "Insurance Portability and Accountability Act of 1996 (HIPAA) and the Health Information "
        "Technology for Economic and Clinical Health Act (HITECH). Vendor is a Business Associate "
        "of Customer.")
    pdf.clause("3.2", "Permitted Uses and Disclosures of PHI",
        "Vendor may use or disclose Protected Health Information (PHI) solely to perform "
        "services under this Agreement, as required by law, for proper management and "
        "administration of Vendor, or as otherwise permitted under 45 CFR Sec. 164.504(e). "
        "Vendor shall not use or disclose PHI in any manner that would violate HIPAA if done "
        "by Customer. All permitted uses and disclosures are strictly enumerated herein.")
    pdf.clause("3.3", "Safeguards for PHI",
        "Vendor shall implement and maintain appropriate administrative, physical, and technical "
        "safeguards to protect PHI from unauthorized use or disclosure in accordance with "
        "45 CFR Sections 164.308, 164.310, and 164.312. Vendor conducts annual risk analysis and "
        "risk management reviews as required under the HIPAA Security Rule.")
    pdf.clause("3.4", "Subcontractor Agreements",
        "Vendor shall ensure that any subcontractor or agent that creates, receives, maintains, "
        "or transmits PHI on behalf of Vendor executes a written subcontractor business associate "
        "agreement imposing the same restrictions and conditions that apply to Vendor under this "
        "Article. Vendor maintains a current register of all such subcontractors.")
    pdf.clause("3.5", "Individual Rights",
        "Vendor shall: (a) provide Customer access to PHI to enable Customer to respond to "
        "individual access requests within the timeframes required by 45 CFR Sec. 164.524; "
        "(b) accommodate requests to amend PHI per 45 CFR Sec. 164.526; (c) document and provide "
        "accountings of disclosures per 45 CFR Sec. 164.528; (d) restrict uses and disclosures "
        "upon Customer's reasonable request.")
    pdf.clause("3.6", "Breach Notification",
        "Vendor shall notify Customer of any Breach of Unsecured PHI without unreasonable delay "
        "and in no case later than five (5) calendar days after discovery. Notice shall include: "
        "identification of affected individuals, description of the breach, types of PHI involved, "
        "steps individuals should take, steps Vendor is taking to investigate and mitigate, "
        "and contact information. Vendor maintains a documented breach notification procedure.")
    pdf.clause("3.7", "Return or Destruction of PHI",
        "Upon termination, Vendor shall return or destroy all PHI received from or on behalf of "
        "Customer within thirty (30) days. If return or destruction is infeasible, Vendor shall "
        "extend protections to such PHI and limit further uses and disclosures, notifying "
        "Customer in writing of the infeasibility and the reasons therefore.")

    pdf.h2("ARTICLE 4 - DATA PROCESSING AGREEMENT (GDPR)")
    pdf.clause("4.1", "Scope and Role",
        "For the purposes of EU General Data Protection Regulation 2016/679 (\"GDPR\"), "
        "Customer is the Data Controller and Vendor is the Data Processor. This Article "
        "constitutes the Data Processing Agreement (DPA) required under GDPR Article 28.")
    pdf.clause("4.2", "Lawful Basis and Purpose Limitation",
        "Vendor shall process personal data only on documented instructions from Customer and "
        "only for the purposes explicitly set out in Schedule C. Vendor confirms it understands "
        "the lawful basis for processing under GDPR Article 6 and will not process data for "
        "any purpose incompatible with those specified. Purpose limitation is strictly enforced.")
    pdf.clause("4.3", "Data Subject Rights",
        "Vendor shall assist Customer in fulfilling obligations to respond to data subject "
        "requests including access (Art. 15), rectification (Art. 16), erasure (Art. 17), "
        "restriction (Art. 18), portability (Art. 20), and objection (Art. 21). Vendor shall "
        "respond to Customer's requests within five (5) business days.")
    pdf.clause("4.4", "Sub-processor Approval",
        "Vendor shall not engage any sub-processor without prior specific or general written "
        "authorization of Customer. Vendor shall notify Customer of intended sub-processor "
        "changes, giving Customer the opportunity to object. Current sub-processors are listed "
        "in Schedule D and updated at least thirty (30) days before any change.")
    pdf.clause("4.5", "Data Breach Notification",
        "In the event of a personal data breach, Vendor shall notify Customer without undue "
        "delay and no later than twenty-four (24) hours after becoming aware of the breach, "
        "enabling Customer to meet its seventy-two (72) hour notification obligation to the "
        "supervisory authority under GDPR Article 33.")
    pdf.clause("4.6", "Security of Processing",
        "Vendor implements appropriate technical and organizational measures per GDPR Article 32, "
        "including: AES-256 encryption at rest and in transit; role-based access controls; "
        "multi-factor authentication; regular penetration testing; employee security training; "
        "and a formal incident response plan reviewed annually.")
    pdf.clause("4.7", "Records of Processing Activities",
        "Vendor maintains a complete record of all processing activities carried out on behalf "
        "of Customer as required by GDPR Article 30(2), including categories of processing, "
        "transfers to third countries, and retention schedules.")
    pdf.clause("4.8", "Return or Deletion of Data",
        "Upon termination of this Agreement, Vendor shall at Customer's choice delete or return "
        "all personal data and delete existing copies within thirty (30) days, unless EU or "
        "member state law requires storage of the personal data.")

    pdf.h2("ARTICLE 5 - SOC 2 TYPE II COMPLIANCE")
    pdf.clause("5.1", "Security Certification",
        "Vendor holds a current SOC 2 Type II certification covering the Security, Availability, "
        "and Confidentiality trust service criteria, audited annually by an independent AICPA "
        "accredited firm. Customer may request the most recent audit report under NDA.")
    pdf.clause("5.2", "Access Controls",
        "Vendor enforces strict role-based access controls. Access to production systems requires "
        "multi-factor authentication. Privileged access is logged, reviewed quarterly, and "
        "immediately revoked upon employee departure. Vendor conducts bi-annual access reviews.")
    pdf.clause("5.3", "Logging and Monitoring",
        "Vendor maintains comprehensive audit logs of all system access and data operations "
        "for a minimum of twelve (12) months. Security Information and Event Management (SIEM) "
        "systems provide real-time alerting on anomalous activity.")
    pdf.clause("5.4", "Business Continuity",
        "Vendor maintains a documented Business Continuity and Disaster Recovery Plan (BCP/DRP) "
        "tested semi-annually. Recovery Time Objective (RTO) is four (4) hours; Recovery Point "
        "Objective (RPO) is one (1) hour. Geographic redundancy is maintained across two "
        "availability zones.")
    pdf.clause("5.5", "Vendor Risk Management",
        "Vendor conducts annual security assessments of all critical third-party vendors "
        "with access to Customer data. Findings are remediated within agreed timelines and "
        "reported to Customer upon request.")
    pdf.clause("5.6", "Change Management",
        "All changes to production systems follow a documented change management process "
        "including: change request, impact assessment, approval by Change Advisory Board, "
        "testing in staging, and post-deployment validation. Emergency changes are documented "
        "within twenty-four (24) hours.")

    pdf.h2("ARTICLE 6 - CONFIDENTIALITY")
    pdf.clause("6.1", "Obligations",
        "Each Party shall hold the other's Confidential Information in strict confidence and "
        "not disclose it to any third party without prior written consent. Each Party shall "
        "use the same degree of care as it uses to protect its own confidential information, "
        "but not less than reasonable care.")
    pdf.clause("6.2", "Exclusions",
        "Confidentiality obligations do not apply to information that: (a) is or becomes "
        "publicly known through no breach of this Agreement; (b) was rightfully in the "
        "receiving Party's possession prior to disclosure; (c) is independently developed "
        "without use of Confidential Information; or (d) is required to be disclosed by law.")

    pdf.h2("ARTICLE 7 - INTELLECTUAL PROPERTY")
    pdf.clause("7.1", "Vendor IP",
        "Vendor retains all intellectual property rights in the Services, platform, and "
        "underlying technology. This Agreement grants Customer a limited, non-exclusive, "
        "non-transferable license to use the Services during the Term.")
    pdf.clause("7.2", "Customer Data",
        "Customer retains all rights, title, and interest in Customer Data. Vendor acquires "
        "no rights in Customer Data except the limited right to process it as necessary to "
        "provide the Services.")

    pdf.h2("ARTICLE 8 - LIABILITY AND INDEMNIFICATION")
    pdf.clause("8.1", "Limitation of Liability",
        "EXCEPT FOR BREACHES OF CONFIDENTIALITY, INDEMNIFICATION OBLIGATIONS, OR GROSS "
        "NEGLIGENCE, NEITHER PARTY SHALL BE LIABLE FOR INDIRECT, INCIDENTAL, OR CONSEQUENTIAL "
        "DAMAGES. EACH PARTY'S TOTAL LIABILITY SHALL NOT EXCEED THE FEES PAID IN THE TWELVE "
        "(12) MONTHS PRECEDING THE CLAIM.")
    pdf.clause("8.2", "Mutual Indemnification",
        "Each Party shall indemnify the other against third-party claims arising from its own "
        "breach of this Agreement, negligence, or willful misconduct. Indemnification is mutual "
        "and balanced, with standard notice and cooperation requirements.")

    pdf.h2("ARTICLE 9 - GOVERNING LAW")
    pdf.clause("9.1", "Governing Law",
        "This Agreement is governed by the laws of the State of Delaware, without regard to "
        "conflicts of law principles. Disputes shall be resolved by binding arbitration under "
        "AAA Commercial Rules in San Francisco, CA.")

    pdf.h2("ARTICLE 10 - GENERAL PROVISIONS")
    pdf.clause("10.1", "Entire Agreement",
        "This Agreement, including all Schedules, constitutes the entire agreement between "
        "the Parties and supersedes all prior understandings.")
    pdf.clause("10.2", "Amendment",
        "Amendments must be in writing and signed by authorized representatives of both Parties.")
    pdf.clause("10.3", "Severability",
        "If any provision is found invalid, the remaining provisions continue in full force.")

    pdf.body(
        "\n\nIN WITNESS WHEREOF, the Parties have executed this Agreement as of the Effective Date.\n\n"
        "SecureCloud Technologies Inc.\nBy: _________________________\n"
        "Name: Jennifer Walsh\nTitle: Chief Executive Officer\nDate: January 1, 2024\n\n"
        "HealthBridge Partners LLC\nBy: _________________________\n"
        "Name: Dr. Michael Chen\nTitle: Chief Information Officer\nDate: January 1, 2024"
    )

    path = OUT_DIR / "TEST_AUTO_APPROVE_SaaS_DPA_2024.pdf"
    pdf.output(str(path))
    print(f"✅  AUTO_APPROVE  → {path}")


# =============================================================================
# 2. MANAGER_REVIEW - Professional Services Agreement (moderate gaps)
#    Target: composite ~73, risk ~25, compliance ~62%, quality ~90%
#    Critical items present (no REJECT), 2 High risk findings
# =============================================================================

def make_manager_review():
    pdf = ContractPDF("SHIELD-TEST-MANAGER-REVIEW-PSA-2024")
    pdf.h1("PROFESSIONAL SERVICES AND SOFTWARE LICENSE AGREEMENT")

    pdf.body(
        "This Professional Services and Software License Agreement (\"Agreement\") is made "
        "as of March 15, 2024 (\"Effective Date\") between:\n\n"
        "Vendor: DataSync Solutions Ltd., a Texas corporation located at 1200 Tech Parkway, "
        "Austin, TX 78701 (\"Vendor\"); and\n\n"
        "Customer: Meridian Healthcare Group Inc., an Illinois corporation located at "
        "900 Medical Center Drive, Chicago, IL 60601 (\"Customer\").\n\n"
        "The Parties agree as follows:"
    )
    pdf.divider()

    pdf.h2("ARTICLE 1 - TERM")
    pdf.clause("1.1", "Term",
        "This Agreement commences on the Effective Date and continues for two (2) years. "
        "Either Party may terminate for convenience with thirty (30) days written notice. "
        "Upon expiration, this Agreement automatically renews for one-year periods unless "
        "notice of non-renewal is given forty-five (45) days in advance.")
    pdf.clause("1.2", "Payment Terms",
        "Customer shall pay invoices within forty-five (45) days. Vendor reserves the right "
        "to adjust pricing annually by up to eight percent (8%) without Customer consent, "
        "applicable to renewal terms only, with thirty (30) days advance notice.")

    pdf.h2("ARTICLE 2 - SERVICES")
    pdf.clause("2.1", "Service Scope",
        "Vendor shall provide software implementation, integration, and ongoing support "
        "services as described in Statement of Work (SOW) documents executed by both Parties.")
    pdf.clause("2.2", "Change Orders",
        "Vendor may modify the scope of services by providing Customer with written notice "
        "of proposed changes. If Customer does not object within ten (10) business days, "
        "changes are deemed accepted. Vendor may adjust fees accordingly.")
    pdf.clause("2.3", "Governing Law",
        "This Agreement shall be governed by the laws of the State of Texas. Disputes shall "
        "be resolved in the state or federal courts located in Austin, Texas.")

    pdf.h2("ARTICLE 3 - HIPAA BUSINESS ASSOCIATE AGREEMENT")
    pdf.clause("3.1", "Business Associate Designation",
        "Vendor is designated as a Business Associate under HIPAA with respect to Protected "
        "Health Information (PHI) it processes on behalf of Customer.")
    pdf.clause("3.2", "Permitted Uses and Disclosures of PHI",
        "Vendor may use PHI only as necessary to perform services under this Agreement. "
        "Additional uses require Customer's prior written approval. Vendor shall not disclose "
        "PHI to third parties except as required by applicable law.")
    pdf.clause("3.3", "Safeguards for PHI",
        "Vendor shall maintain reasonable and appropriate administrative, physical, and "
        "technical safeguards to prevent unauthorized access to PHI, consistent with HIPAA "
        "Security Rule requirements at 45 CFR Sections 164.308, 164.310, 164.312.")
    pdf.clause("3.4", "Breach Notification",
        "In the event of a breach of unsecured PHI, Vendor shall notify Customer within "
        "ten (10) business days of discovery. Vendor shall provide available information "
        "regarding the nature and scope of the breach.")
    pdf.clause("3.5", "Return or Destruction of PHI",
        "Upon termination, Vendor shall return or destroy all PHI within sixty (60) days "
        "as directed by Customer, unless retention is required by law.")
    pdf.clause("3.6", "Subcontractor Agreements",
        "Vendor shall ensure subcontractors handling PHI are bound by appropriate data "
        "protection obligations consistent with this Agreement.")

    pdf.h2("ARTICLE 4 - GDPR DATA PROCESSING")
    pdf.clause("4.1", "Data Processing Agreement",
        "To the extent Vendor processes personal data of EU data subjects on behalf of "
        "Customer, this Article constitutes the Data Processing Agreement (DPA) under "
        "GDPR Article 28. Customer is Controller; Vendor is Processor.")
    pdf.clause("4.2", "Lawful Basis and Purpose Limitation",
        "Vendor shall process personal data only on Customer's documented instructions and "
        "only for the specific purposes set out in Schedule C: software implementation, "
        "integration support, and system maintenance. The subject matter of processing is "
        "healthcare operations data. The duration of processing is coterminous with this "
        "Agreement. Categories of data subjects include Customer employees and patients. "
        "Types of personal data include operational records and system usage data. Vendor "
        "shall not process personal data for any purpose incompatible with those specified "
        "herein. Customer confirms it has identified a lawful basis under GDPR Article 6.")
    pdf.clause("4.3", "Security Measures",
        "Vendor implements appropriate technical and organizational security measures "
        "to protect personal data against unauthorized processing and accidental loss.")
    pdf.clause("4.4", "Data Breach Notification",
        "Vendor shall notify Customer of personal data breaches without undue delay and in no "
        "case later than seventy-two (72) hours after becoming aware of the breach, enabling "
        "Customer to meet its notification obligations to supervisory authorities under GDPR "
        "Article 33. Notification shall include: the nature of the breach, categories and "
        "approximate number of data subjects and records concerned, likely consequences, and "
        "measures taken or proposed to address the breach.")
    pdf.clause("4.5", "Sub-processor Approval",
        "Vendor shall obtain Customer's written approval before engaging sub-processors. "
        "A list of current sub-processors is available upon request.")
    pdf.clause("4.6", "Return or Deletion",
        "Upon termination, Vendor shall delete personal data within forty-five (45) days "
        "unless retention is required by applicable law.")

    pdf.h2("ARTICLE 5 - SECURITY STANDARDS")
    pdf.clause("5.1", "Access Controls",
        "Vendor maintains role-based access controls and requires multi-factor authentication "
        "for access to systems processing Customer data.")
    pdf.clause("5.2", "Incident Response",
        "Vendor maintains a documented incident response plan and shall involve Customer "
        "in the response process for incidents affecting Customer data.")
    pdf.clause("5.3", "Security Audit",
        "Vendor undergoes annual third-party security assessments. Customer may request "
        "a summary of findings subject to a mutual non-disclosure agreement.")

    pdf.h2("ARTICLE 6 - INTELLECTUAL PROPERTY AND DATA")
    pdf.clause("6.1", "Work Product Ownership",
        "All work product, deliverables, and custom developments created by Vendor "
        "specifically for Customer under a SOW shall be owned by Vendor unless explicitly "
        "designated as Customer-owned in the applicable SOW. Customer receives a perpetual "
        "license to use such work product for its internal business purposes.")
    pdf.clause("6.2", "Customer Data",
        "Customer retains ownership of its data. Vendor may use aggregated and anonymized "
        "Customer data to improve its platform and services without restriction, provided "
        "such data cannot reasonably be used to identify Customer or its clients.")

    pdf.h2("ARTICLE 7 - LIABILITY")
    pdf.clause("7.1", "Limitation of Liability",
        "Vendor's maximum aggregate liability for any claims under this Agreement shall not "
        "exceed the greater of: (a) fees paid in the preceding six (6) months, or (b) "
        "fifty thousand dollars ($50,000). This cap applies regardless of the theory of "
        "liability, including negligence or breach of contract.")
    pdf.clause("7.2", "Consequential Damages Waiver",
        "Neither Party shall be liable for indirect, incidental, special, punitive, or "
        "consequential damages, including loss of profits or data.")
    pdf.clause("7.3", "Indemnification by Customer",
        "Customer shall indemnify Vendor against any claims arising from: (a) Customer's "
        "misuse of the Services; (b) Customer's breach of this Agreement; (c) any third-party "
        "claims related to Customer's data or instructions to Vendor. This indemnification "
        "obligation is not reciprocal - Vendor has no corresponding obligation.")

    pdf.h2("ARTICLE 8 - GENERAL")
    pdf.clause("8.1", "Entire Agreement",
        "This Agreement constitutes the entire agreement between the Parties.")
    pdf.clause("8.2", "Amendments",
        "Vendor may amend this Agreement by providing thirty (30) days written notice. "
        "Customer's continued use of Services after the notice period constitutes acceptance.")

    pdf.body(
        "\n\nIN WITNESS WHEREOF, the Parties have executed this Agreement as of the date first written.\n\n"
        "DataSync Solutions Ltd.\nBy: _________________________\n"
        "Name: Robert Martinez\nTitle: President\nDate: March 15, 2024\n\n"
        "Meridian Healthcare Group Inc.\nBy: _________________________\n"
        "Name: Sarah Johnson\nTitle: VP of Operations\nDate: March 15, 2024"
    )

    path = OUT_DIR / "TEST_MANAGER_REVIEW_PSA_2024.pdf"
    pdf.output(str(path))
    print(f"✅  MANAGER_REVIEW → {path}")


# =============================================================================
# 3. LEGAL_REVIEW - High-Risk Distribution & Data Agreement
#    Target: composite ~50, risk ~45, compliance ~28%, quality ~80%
#    Critical items barely present (avoid REJECT override), many gaps,
#    4+ High risk findings
# =============================================================================

def make_legal_review():
    pdf = ContractPDF("SHIELD-TEST-LEGAL-REVIEW-DISTRIBUTION-2024")
    pdf.h1("DATA DISTRIBUTION AND ANALYTICS SERVICES AGREEMENT")

    pdf.body(
        "This Data Distribution and Analytics Services Agreement (\"Agreement\") is entered "
        "into as of June 1, 2024 between:\n\n"
        "Vendor: GlobalData Exchange Corp., a Nevada corporation at 400 Commerce Blvd, "
        "Las Vegas, NV 89101 (\"Vendor\"); and\n\n"
        "Customer: Regional Medical Associates LLC, a Florida LLC at 700 Health Ave, "
        "Miami, FL 33101 (\"Customer\").\n\n"
        "Governing Law: State of Nevada. Effective Date: June 1, 2024."
    )
    pdf.divider()

    pdf.h2("ARTICLE 1 - TERM AND PAYMENT")
    pdf.clause("1.1", "Term",
        "This Agreement commences on the Effective Date and continues for five (5) years, "
        "automatically renewing for successive five-year periods unless terminated with "
        "one hundred eighty (180) days written notice prior to expiration.")
    pdf.clause("1.2", "Fees and Unilateral Price Changes",
        "Customer shall pay all fees within fifteen (15) days of invoice. Vendor may "
        "increase fees at any time by providing written notice, with increases effective "
        "upon the next billing cycle. Customer's continued use constitutes acceptance of "
        "any fee increase. Vendor does not guarantee fee stability for any period.")
    pdf.clause("1.3", "Late Payment Penalties",
        "Invoices not paid within fifteen (15) days accrue interest at eighteen percent "
        "(18%) per annum, compounded monthly. Vendor may suspend services immediately "
        "upon any payment default without further notice and without liability to Customer.")

    pdf.h2("ARTICLE 2 - DATA SERVICES AND OBLIGATIONS")
    pdf.clause("2.1", "Data Distribution",
        "Vendor shall provide Customer with access to Vendor's proprietary data sets, "
        "analytics tools, and distribution APIs as specified in Exhibit A. Vendor reserves "
        "the right to modify, restrict, or discontinue any data set or feature at any time "
        "with or without notice, without liability to Customer.")
    pdf.clause("2.2", "Third-Party Data Sharing",
        "Customer acknowledges that Vendor may share Customer's usage data, query patterns, "
        "and aggregated business intelligence with third-party partners and affiliates for "
        "product development, marketing, and monetization purposes. Customer consents to "
        "such sharing by executing this Agreement.")
    pdf.clause("2.3", "Data Quality Disclaimer",
        "Vendor provides data on an as-is basis and makes no warranties regarding accuracy, "
        "completeness, or fitness for any particular purpose. Customer assumes all risk "
        "associated with reliance on Vendor-provided data.")
    pdf.clause("2.4", "Sole and Exclusive Provider",
        "During the Term and for two (2) years thereafter, Customer shall use Vendor as its "
        "sole and exclusive provider of data distribution and analytics services in the "
        "healthcare sector. Customer shall not engage any competing service provider. "
        "Breach of this exclusivity provision entitles Vendor to liquidated damages equal "
        "to the total fees that would have been payable for the remainder of the Term.")

    pdf.h2("ARTICLE 3 - HIPAA BUSINESS ASSOCIATE AGREEMENT")
    pdf.clause("3.1", "Business Associate Agreement",
        "This Article constitutes the Business Associate Agreement (BAA) required under the "
        "Health Insurance Portability and Accountability Act (HIPAA). Vendor is a Business "
        "Associate of Customer to the extent it creates, receives, maintains, or transmits "
        "Protected Health Information (PHI) in performing services under this Agreement.")
    pdf.clause("3.2", "PHI Safeguard Measures",
        "Vendor shall implement safeguards for PHI that Vendor determines, in its sole "
        "discretion, to be reasonable and appropriate given Vendor's operational requirements. "
        "Vendor's specific HIPAA safeguard obligations are limited to those expressly required "
        "by applicable law and shall not expand Vendor's liability beyond Article 8. "
        "Customer acknowledges that Vendor's safeguard standards may change over time.")
    pdf.clause("3.3", "Breach Notification",
        "Vendor shall notify Customer of any confirmed breach of unsecured PHI within thirty "
        "(30) days after Vendor's internal legal team concludes its investigation and confirms "
        "a reportable breach has occurred. Vendor shall have no obligation to notify Customer "
        "of suspected or unconfirmed breaches. Vendor's notification obligations are limited "
        "to breaches directly attributable to Vendor's gross negligence.")

    pdf.h2("ARTICLE 4 - GDPR PROVISIONS")
    pdf.clause("4.1", "Data Processing Agreement",
        "This Article constitutes the Data Processing Agreement (DPA) required under GDPR "
        "Article 28 for processing of EU personal data. Customer is the Data Controller; "
        "Vendor is the Data Processor. Vendor's obligations under this DPA are limited to "
        "those expressly set forth herein and do not incorporate by reference the full "
        "Article 28 requirements beyond what is explicitly stated.")
    pdf.clause("4.2", "Processing Basis",
        "Customer represents it has identified a lawful basis for all personal data processing "
        "under this Agreement. Vendor processes data solely on Customer's instructions. "
        "Customer is solely responsible for ensuring processing is lawful. Purpose limitation "
        "and documentation of processing activities are Customer's sole responsibility.")
    pdf.clause("4.3", "Data Breach Notification",
        "Vendor shall notify Customer of personal data breaches without undue delay and "
        "in no case later than seventy-two (72) hours after becoming aware, enabling Customer "
        "to meet its GDPR Article 33 supervisory authority notification obligations. "
        "Notification shall be limited to confirmed incidents and shall not require Vendor "
        "to disclose information that could compromise Vendor's security investigations.")
    pdf.clause("4.4", "Security Measures",
        "Vendor applies industry-standard security measures to personal data. Specific "
        "technical controls are determined by Vendor at its sole discretion and may change "
        "without notice based on Vendor's operational requirements. Vendor provides no "
        "warranties as to the adequacy of such measures for Customer's specific risk profile.")

    pdf.h2("ARTICLE 5 - INTELLECTUAL PROPERTY")
    pdf.clause("5.1", "Broad IP Assignment",
        "Any data, insights, reports, analyses, algorithms, models, or derivative works "
        "developed by Customer using Vendor's platform or incorporating Vendor's data shall "
        "be owned exclusively by Vendor. Customer irrevocably assigns all such intellectual "
        "property to Vendor, including any inventions, trade secrets, or copyrightable works. "
        "Customer waives all moral rights in such assigned works.")
    pdf.clause("5.2", "License Back",
        "Vendor grants Customer a limited, revocable license to use Customer's own assigned "
        "IP for internal purposes only during the Term. Upon termination, this license "
        "immediately terminates and Customer must cease all use of assigned IP.")

    pdf.h2("ARTICLE 6 - CONFIDENTIALITY (LIMITED)")
    pdf.clause("6.1", "Customer Confidentiality",
        "Customer agrees to keep Vendor's pricing, methods, and platform details confidential "
        "for five (5) years. Vendor has no reciprocal confidentiality obligation with respect "
        "to Customer's business information, data patterns, or operational details.")

    pdf.h2("ARTICLE 7 - NON-COMPETE AND NON-SOLICITATION")
    pdf.clause("7.1", "Non-Compete",
        "During the Term and for three (3) years after termination, Customer shall not, "
        "directly or indirectly, develop, market, or commercialize any product or service "
        "that competes with Vendor's platform in any market where Vendor operates. This "
        "restriction applies globally and across all healthcare data analytics verticals.")
    pdf.clause("7.2", "Non-Solicitation",
        "Customer shall not solicit or hire any Vendor employee or contractor for two (2) "
        "years after termination. Breach entitles Vendor to liquidated damages of $250,000 "
        "per solicitation.")

    pdf.h2("ARTICLE 8 - LIABILITY AND INDEMNIFICATION")
    pdf.clause("8.1", "Uncapped Vendor Indemnification by Customer",
        "Customer shall indemnify, defend, and hold harmless Vendor, its officers, directors, "
        "employees, agents, successors, and assigns from and against any and all claims, "
        "damages, losses, liabilities, costs, and expenses (including attorneys' fees) of "
        "any nature arising from: (a) Customer's use of the Services; (b) Customer's breach "
        "of any representation or warranty; (c) any third-party claims related to Customer's "
        "data; (d) Customer's business operations; or (e) any regulatory investigations "
        "related to Customer's use of data. THIS INDEMNIFICATION IS UNCAPPED AND UNLIMITED.")
    pdf.clause("8.2", "Limitation of Vendor Liability",
        "Vendor's total liability to Customer for any cause of action shall not exceed "
        "one thousand dollars ($1,000). This cap applies in aggregate to all claims under "
        "this Agreement regardless of the number of claims or theories of liability.")
    pdf.clause("8.3", "No Warranties",
        "VENDOR PROVIDES ALL SERVICES AND DATA ON AN AS-IS, AS-AVAILABLE BASIS. VENDOR "
        "EXPRESSLY DISCLAIMS ALL WARRANTIES, EXPRESS, IMPLIED, OR STATUTORY, INCLUDING "
        "WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.")

    pdf.h2("ARTICLE 9 - TERMINATION")
    pdf.clause("9.1", "Termination by Vendor",
        "Vendor may terminate this Agreement immediately and without liability: (a) at "
        "Vendor's sole discretion for any reason or no reason by providing ten (10) days "
        "notice; (b) immediately if Customer's financial condition deteriorates; (c) if "
        "Vendor undergoes a change in business strategy; or (d) if Vendor discontinues "
        "any product or service Customer relies upon.")
    pdf.clause("9.2", "Effects of Termination",
        "Upon termination: (a) all Customer licenses immediately terminate; (b) Customer "
        "must pay all outstanding and future fees through the original Term end date; "
        "(c) Vendor may retain all Customer data indefinitely for Vendor's business purposes; "
        "(d) Customer's IP assignment under Article 5 survives termination permanently.")

    pdf.h2("ARTICLE 10 - GENERAL")
    pdf.clause("10.1", "Amendment",
        "Vendor may amend this Agreement at any time. Amendments take effect upon posting "
        "to Vendor's website. Customer's continued use constitutes acceptance.")
    pdf.clause("10.2", "Entire Agreement",
        "This Agreement constitutes the entire agreement between the Parties.")

    pdf.body(
        "\n\nIN WITNESS WHEREOF, the Parties have executed this Agreement.\n\n"
        "GlobalData Exchange Corp.\nBy: _________________________\n"
        "Name: Thomas Lee\nTitle: Chief Revenue Officer\nDate: June 1, 2024\n\n"
        "Regional Medical Associates LLC\nBy: _________________________\n"
        "Name: Dr. Patricia Williams\nTitle: Managing Director\nDate: June 1, 2024"
    )

    path = OUT_DIR / "TEST_LEGAL_REVIEW_Distribution_2024.pdf"
    pdf.output(str(path))
    print(f"✅  LEGAL_REVIEW  → {path}")


if __name__ == "__main__":
    make_auto_approve()
    make_manager_review()
    make_legal_review()
    print(f"\nAll PDFs saved to: {OUT_DIR.resolve()}")
