import streamlit as st
import datetime
import re
import io
import base64
import sqlite3
import json
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="ECHS Feedback Form Generator", layout="wide")

# Custom CSS for UI adjustments
st.markdown("""
<style>
    div[data-testid="column"] button {
        padding: 3px 8px !important;
        font-size: 13px !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- DATABASE SETUP ----------------
DB_FILE = "echs_forms.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS forms (
            claim_id TEXT PRIMARY KEY,
            patient_name TEXT,
            data_json TEXT
        )
    ''')
    conn.commit()
    conn.close()

def load_forms_from_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT claim_id, data_json FROM forms")
    rows = c.fetchall()
    conn.close()
    
    forms = {}
    for claim_id, data_json in rows:
        forms[claim_id] = json.loads(data_json)
    return forms

def save_form_to_db(claim_id, patient_name, form_data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    data_json = json.dumps(form_data)
    c.execute('''
        INSERT OR REPLACE INTO forms (claim_id, patient_name, data_json)
        VALUES (?, ?, ?)
    ''', (claim_id, patient_name, data_json))
    conn.commit()
    conn.close()

def delete_form_from_db(claim_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM forms WHERE claim_id = ?", (claim_id,))
    conn.commit()
    conn.close()

# Initialize Database
init_db()

# Initialize Session State from DB
if "saved_forms" not in st.session_state:
    st.session_state["saved_forms"] = load_forms_from_db()
if "delete_target" not in st.session_state:
    st.session_state["delete_target"] = None
if "view_target" not in st.session_state:
    st.session_state["view_target"] = None
if "editing_claim_id" not in st.session_state:
    st.session_state["editing_claim_id"] = None

def sync_esm_name():
    if st.session_state.get("relation_input") == "SELF":
        st.session_state["esm_name_input"] = st.session_state.get("patient_name_input", "")

# PDF Generator Function (EXACT SAME UNTOUCHED LAYOUT)
def generate_pdf_bytes(form_data):
    buffer = io.BytesIO()
    NARROW_MARGIN = 36  # 1.27 cm
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=NARROW_MARGIN,
        leftMargin=NARROW_MARGIN,
        topMargin=NARROW_MARGIN,
        bottomMargin=NARROW_MARGIN
    )
    elements = []
    styles = getSampleStyleSheet()

    # Custom Styles
    style_center = ParagraphStyle('Center', parent=styles['Normal'], alignment=1, fontSize=10, leading=12)
    style_title = ParagraphStyle('Title', parent=styles['Normal'], alignment=1, fontSize=22, leading=24, fontName='Helvetica-Bold')
    style_subtitle = ParagraphStyle('SubTitle', parent=styles['Normal'], alignment=1, fontSize=18, leading=20, fontName='Helvetica-Bold')
    style_bold = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=9.5, leading=11.5, fontName='Helvetica-Bold')
    style_normal = ParagraphStyle('NormalText', parent=styles['Normal'], fontSize=9, leading=11)
    style_small = ParagraphStyle('SmallText', parent=styles['Normal'], fontSize=8.5, leading=10.5, fontName='Helvetica-Oblique')
    style_table_cell = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8.5, leading=10.5, alignment=1)
    style_table_left = ParagraphStyle('CellLeft', parent=styles['Normal'], fontSize=8.5, leading=10.5, alignment=0)

    # 1. Compact Claim ID Box
    claim_text = f"CLAIM ID : <b>{form_data['claim_id']}</b>"
    claim_p = Paragraph(claim_text, ParagraphStyle('ClaimStyle', fontSize=9, fontName='Helvetica', alignment=1))
    
    claim_table = Table([[ "", claim_p ]], colWidths=[382, 140])
    claim_table.setStyle(TableStyle([
        ('BOX', (1,0), (1,0), 0.5, colors.black),
        ('INNERGRID', (1,0), (1,0), 0.5, colors.black),
        ('PADDING', (1,0), (1,0), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(claim_table)
    elements.append(Spacer(1, 4))

    # 2. Header Section
    elements.append(Paragraph("UJALA CYGNUS SUPERSPECIALITY HOSPITAL", style_title))
    elements.append(Paragraph("REWARI, HARYANA", style_center))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("<u>FEEDBACK FORM</u>", style_subtitle))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph("<u>EX-SERVICEMEN CONTRIBUTORY HEALTH SCHEME</u>", ParagraphStyle('Sub', parent=style_center, fontSize=9.5, leading=11.5)))
    elements.append(Spacer(1, 10))

    # 3. Patient Details
    col_w = [110, 151] 

    def make_row(label, val):
        return [
            Paragraph(f"{label}", style_normal),
            Paragraph(f": <b><u>{val}</u></b>", style_normal)
        ]

    left_details = Table([
        make_row("Name of Patient", form_data['patient_name']),
        make_row("Service No.", form_data['service_no']),
        make_row("Rank", form_data['rank']),
        make_row("Date of Admission", form_data['adm_str'])
    ], colWidths=col_w)

    right_details = Table([
        make_row("Relation with ESM", form_data['relation']),
        make_row("Registration No.", form_data['formatted_echs']),
        make_row("ESM NAME", form_data['esm_name']),
        make_row("Date of Discharge", form_data['dis_str'])
    ], colWidths=col_w)

    t_style = TableStyle([
        ('PADDING', (0,0), (-1,-1), 2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])
    left_details.setStyle(t_style)
    right_details.setStyle(t_style)

    grid_table = Table([[left_details, right_details]], colWidths=[261, 261])
    grid_table.setStyle(TableStyle([
        ('PADDING', (0,0), (-1,-1), 0),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(grid_table)
    elements.append(Spacer(1, 10))

    # 4. PART-II Header
    elements.append(Paragraph("<b>PART-II (To be filed by the Patient at the time of Discharge)</b>", style_bold))
    elements.append(Paragraph("<i>Note:- Kindly tick mark on a scale of where 1=Poor, 2=Unsatisfactory, 3=Fair, 4=Good, 5=Excellent.</i>", style_small))
    elements.append(Spacer(1, 6))

    # 5. Rating Table
    table_data = [[
        Paragraph("<b>S. NO.</b>", style_table_cell),
        Paragraph("<b>SERVICES OFFERED BY HOSPITAL</b>", style_table_cell),
        Paragraph("<b>1</b>", style_table_cell),
        Paragraph("<b>2</b>", style_table_cell),
        Paragraph("<b>3</b>", style_table_cell),
        Paragraph("<b>4</b>", style_table_cell),
        Paragraph("<b>5</b>", style_table_cell)
    ]]

    for idx, q in enumerate(form_data['questions'], 1):
        q_clean = q.split(". ", 1)[1]
        r_val = form_data['ratings'][q]
        row = [
            Paragraph(str(idx), style_table_cell),
            Paragraph(q_clean, style_table_left),
            Paragraph("✓" if r_val == 1 else "", style_table_cell),
            Paragraph("✓" if r_val == 2 else "", style_table_cell),
            Paragraph("✓" if r_val == 3 else "", style_table_cell),
            Paragraph("✓" if r_val == 4 else "", style_table_cell),
            Paragraph("✓" if r_val == 5 else "", style_table_cell)
        ]
        table_data.append(row)

    table_data.append([
        "", Paragraph("<b>OPINION OF PATIENT</b>", style_table_left),
        Paragraph("<b>Yes</b>", style_table_cell), "",
        Paragraph("<b>No</b>", style_table_cell), "", ""
    ])
    table_data.append([
        "9", Paragraph("WAS THE DURATION OF HOSPITAL STAY JUSTIFIED?", style_table_left),
        Paragraph("✓" if form_data['q9'] == "Yes" else "", style_table_cell), "",
        Paragraph("✓" if form_data['q9'] == "No" else "", style_table_cell), "", ""
    ])
    table_data.append([
        "10", Paragraph("WAS THERE A TENDANCY TO OVER-INVESTIGATE OR OVER-TREAT?", style_table_left),
        Paragraph("✓" if form_data['q10'] == "Yes" else "", style_table_cell), "",
        Paragraph("✓" if form_data['q10'] == "No" else "", style_table_cell), "", ""
    ])

    ratings_table = Table(table_data, colWidths=[30, 220, 22, 22, 22, 22, 22], hAlign='LEFT')
    ratings_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ('SPAN', (2,9), (3,9)),
        ('SPAN', (4,9), (6,9)),
        ('SPAN', (2,10), (3,10)),
        ('SPAN', (4,10), (6,10)),
        ('SPAN', (2,11), (3,11)),
        ('SPAN', (4,11), (6,11)),
        ('PADDING', (0,0), (-1,-1), 2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(ratings_table)
    elements.append(Spacer(1, 8))

    # 6. Remarks & Station HQ Section
    field_style = ParagraphStyle('FieldLabel', parent=style_normal, fontSize=9.5, leading=11)

    def inline_line(label_text, label_w, line_w):
        t = Table([[Paragraph(label_text, field_style), ""]], colWidths=[label_w, line_w], hAlign='LEFT')
        t.setStyle(TableStyle([
            ('PADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('LINEBELOW', (1,0), (1,0), 0.75, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ]))
        return t

    full_line = Table([[""]], colWidths=[480], hAlign='LEFT')
    full_line.setStyle(TableStyle([
        ('PADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LINEBELOW', (0,0), (0,0), 0.75, colors.black),
    ]))

    part2_header = Paragraph("<b>PART-II (To be filed by station Headquarters)</b>", ParagraphStyle('CenterBold', parent=style_center, fontName='Helvetica-Bold', fontSize=10, leading=12))

    section6_box = Table([
        [inline_line("11. Remark(s) Suggestion(s) by the Patient:", 210, 270)],
        [full_line],
        [Spacer(1, 2)],
        [part2_header],
        [Spacer(1, 2)],
        [inline_line("1. Comments :", 78, 402)],
        [inline_line("2. Action Taken :", 88, 392)],
        [inline_line("3. Forwarded To :", 90, 390)]
    ], colWidths=[522], hAlign='LEFT')

    section6_box.setStyle(TableStyle([
        ('PADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))

    elements.append(section6_box)
    elements.append(Spacer(1, 8))

    # 7. Declaration & Signature
    style_decl_head = ParagraphStyle('DecHead', parent=style_center, fontName='Helvetica-Bold', fontSize=10.5, leading=12.5)
    style_decl_body = ParagraphStyle('JustifyDecl', parent=style_normal, fontSize=10, leading=13, alignment=4)

    elements.append(Paragraph("<u><b>DECLARATION</b></u>", style_decl_head))
    elements.append(Spacer(1, 4))
    
    decl_text = f"According to the Referral from ECHS Polyclinic <b><u>{form_data['polyclinic']}</u></b>, I have obtained treatment from Ujala Cygnus Superspeciality Hospital Rewari (Haryana) w.e.f. <b><u>{form_data['adm_str']}</u></b> to <b><u>{form_data['dis_str']}</u></b> hereby declaration that not paid any amount to the hospital in this regard."
    elements.append(Paragraph(decl_text, style_decl_body))
    elements.append(Spacer(1, 22))

    sig_text = "__________________________<br/><b>Patient / Attendant Signature</b>"
    elements.append(Paragraph(sig_text, ParagraphStyle('RightBold', parent=style_normal, alignment=2, leading=13)))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# Main Navigation
st.sidebar.title("📌 Main Menu")
menu = st.sidebar.radio("Go to:", [
    "📝 Generate New Feedback Form", 
    "✏️ Edit Filled Forms", 
    "📁 Saved Feedback Forms"
])


# ---------------- FUNCTION FOR FORM INPUT UI ----------------
def render_form_ui(is_editing=False):
    editing_id = st.session_state.get("editing_claim_id", None) if is_editing else None
    edit_data = st.session_state["saved_forms"].get(editing_id, {}) if editing_id else {}

    if is_editing and editing_id:
        st.info(f"✏️ **Editing Saved Form for Claim ID:** {editing_id}")

    st.subheader("Header Details")
    claim_id_raw = st.text_input("CLAIM ID (Exact 8 Digits)", value=editing_id if editing_id else "", max_chars=8, placeholder="12345678", disabled=bool(editing_id))
    claim_id = re.sub(r"\D", "", claim_id_raw)

    col1, col2 = st.columns(2)
    with col1:
        patient_name = st.text_input("Name of Patient", value=edit_data.get("patient_name", ""), key="patient_name_input", on_change=sync_esm_name).upper()
        service_no = st.text_input("Service No.", value=edit_data.get("service_no", "")).upper()
        rank = st.text_input("Rank", value=edit_data.get("rank", "")).upper()
        
        adm_val = datetime.datetime.strptime(edit_data["adm_str"], '%d/%m/%Y').date() if edit_data.get("adm_str") else datetime.date.today()
        admission_date = st.date_input("Date of Admission", value=adm_val, format="DD/MM/YYYY")

    with col2:
        def_rel = edit_data.get("relation", "")
        rel_opts = ["", "SELF", "SPOUSE", "FATHER", "MOTHER", "SON", "DAUGHTER"]
        rel_idx = rel_opts.index(def_rel) if def_rel in rel_opts else 0

        relation = st.selectbox("Relation with ESM", rel_opts, index=rel_idx, key="relation_input", on_change=sync_esm_name)
        
        def_echs = edit_data.get("formatted_echs", "").replace(" ", "")
        echs_raw = st.text_input("Registration No. (14 Characters)", value=def_echs, max_chars=14, placeholder="JA000098765738").upper().replace(" ", "")
        
        if len(echs_raw) == 14:
            formatted_echs = f"{echs_raw[:2]} {echs_raw[2:6]} {echs_raw[6:10]} {echs_raw[10:14]}"
        else:
            formatted_echs = echs_raw

        esm_name = st.text_input("ESM NAME", value=edit_data.get("esm_name", ""), key="esm_name_input").upper()
        
        dis_val = datetime.datetime.strptime(edit_data["dis_str"], '%d/%m/%Y').date() if edit_data.get("dis_str") else datetime.date.today()
        discharge_date = st.date_input("Date of Discharge", value=dis_val, format="DD/MM/YYYY")

    st.subheader("PART-II (Feedback Ratings)")
    questions = [
        "1. RECEPTION AT THE TIME OF ADMISSION",
        "2. WAITING INVOLVE BEFORE GETTING ADMISSION",
        "3. PROMPTNESS IN INSTITUTION OF TREATMENT",
        "4. ATTITUDE OF ATTENDING DOCTOR'S",
        "5. ATTITUDE OF NURSING STAFF",
        "6. ATTITUDE OF NON-MEDICAL STAFF",
        "7. GENUINENESS OF TREATMENT OFFERED",
        "8. COMMUNICATION REGARDING NECESSARY OF EACH PROCEDURE"
    ]
    
    ratings = {}
    prev_ratings = edit_data.get("ratings", {})
    for q in questions:
        cur_r = prev_ratings.get(q, None)
        ratings[q] = st.radio(q, [None, 1, 2, 3, 4, 5], index=[None, 1, 2, 3, 4, 5].index(cur_r), horizontal=True, format_func=lambda x: "None" if x is None else str(x))

    st.subheader("Opinion of Patient")
    prev_q9 = edit_data.get("q9", None)
    prev_q10 = edit_data.get("q10", None)
    
    q9 = st.radio("9. WAS THE DURATION OF HOSPITAL STAY JUSTIFIED?", [None, "Yes", "No"], index=[None, "Yes", "No"].index(prev_q9), horizontal=True, format_func=lambda x: "None" if x is None else str(x))
    q10 = st.radio("10. WAS THERE A TENDANCY TO OVER-INVESTIGATE OR OVER-TREAT?", [None, "Yes", "No"], index=[None, "Yes", "No"].index(prev_q10), horizontal=True, format_func=lambda x: "None" if x is None else str(x))

    st.subheader("Declaration Details")
    polyclinic = st.text_input("ECHS Polyclinic Name", value=edit_data.get("polyclinic", "")).upper()

    btn_label = "✏️ Save Corrections" if is_editing else "💾 Save Feedback Form"
    if st.button(btn_label, type="primary"):
        if not is_editing and claim_id in st.session_state["saved_forms"]:
            st.error(f"⚠️ CLAIM ID '{claim_id}' pehle se saved hai!")
        elif not claim_id or len(claim_id) != 8:
            st.error("⚠️ CLAIM ID me exact 8 DIGITS hone chahiye.")
        elif echs_raw and len(echs_raw) != 14:
            st.error("⚠️ Registration No. me exact 14 characters hone chahiye.")
        else:
            form_data = {
                "claim_id": claim_id,
                "patient_name": patient_name,
                "relation": relation,
                "service_no": service_no,
                "rank": rank,
                "formatted_echs": formatted_echs,
                "esm_name": esm_name,
                "adm_str": admission_date.strftime('%d/%m/%Y'),
                "dis_str": discharge_date.strftime('%d/%m/%Y'),
                "questions": questions,
                "ratings": ratings,
                "q9": q9,
                "q10": q10,
                "polyclinic": polyclinic
            }
            # Save to Database permanently
            save_form_to_db(claim_id, patient_name, form_data)
            st.session_state["saved_forms"][claim_id] = form_data
            st.session_state["editing_claim_id"] = None
            st.success(f"✅ Form successfully saved for Claim ID: {claim_id}")


# ---------------- PAGE 1: GENERATE NEW FORM ----------------
if menu == "📝 Generate New Feedback Form":
    st.title("📋 ECHS Feedback Form Generator")
    st.session_state["editing_claim_id"] = None
    render_form_ui(is_editing=False)


# ---------------- PAGE 2: EDIT FILLED FORMS ----------------
elif menu == "✏️ Edit Filled Forms":
    st.title("✏️ Edit / Correct Saved Forms")
    saved_dict = st.session_state["saved_forms"]

    if not saved_dict:
        st.info("Koi saved form nahi mila. Pehle form bharein.")
    else:
        st.write("Edit / Correction ke liye niche kisi bhi **Claim ID** par click karein:")
        
        for c_id, data in saved_dict.items():
            col_a, col_b = st.columns([1, 3])
            p_name = data.get("patient_name", "UNKNOWN")
            
            if col_a.button(f"🆔 {c_id}", key=f"edit_btn_{c_id}"):
                st.session_state["editing_claim_id"] = c_id
                st.rerun()
            col_b.write(f"👤 **Patient Name:** {p_name}")
            st.divider()

        if st.session_state.get("editing_claim_id"):
            st.divider()
            render_form_ui(is_editing=True)


# ---------------- PAGE 3: SAVED FORMS LIST ----------------
elif menu == "📁 Saved Feedback Forms":
    st.title("📁 Saved Feedback Forms")
    saved_dict = st.session_state["saved_forms"]

    if not saved_dict:
        st.info("Koi form save nahi hai.")
    else:
        if st.session_state["delete_target"]:
            del_id = st.session_state["delete_target"]
            st.warning(f"⚠️ Are you sure you want to delete form for Claim ID: **{del_id}**?")
            c_yes, c_no = st.columns([1, 5])
            if c_yes.button("✅ Yes, Delete", type="primary"):
                # Delete from SQLite Database
                delete_form_from_db(del_id)
                del st.session_state["saved_forms"][del_id]
                st.session_state["delete_target"] = None
                st.success(f"Claim ID {del_id} deleted successfully.")
                st.rerun()
            if c_no.button("❌ Cancel"):
                st.session_state["delete_target"] = None
                st.rerun()
            st.divider()

        if st.session_state["view_target"] and st.session_state["view_target"] in saved_dict:
            v_id = st.session_state["view_target"]
            v_data = saved_dict[v_id]
            pdf_bytes = generate_pdf_bytes(v_data)

            @st.dialog(f"📄 Preview Form - Claim ID: {v_id}", width="large")
            def show_pdf_dialog():
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                pdf_display = f'<object data="data:application/pdf;base64,{base64_pdf}" type="application/pdf" width="100%" height="520px"><p>Your browser does not support inline PDFs. <a href="data:application/pdf;base64,{base64_pdf}" download="ECHS_Form_{v_id}.pdf">Click here to download PDF</a></p></object>'
                st.markdown(pdf_display, unsafe_allow_html=True)
                
                st.divider()
                col_d1, col_d2 = st.columns([1, 1])
                with col_d1:
                    st.download_button(
                        label="📥 Download PDF to Print",
                        data=pdf_bytes,
                        file_name=f"ECHS_Form_{v_id}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                with col_d2:
                    if st.button("❌ Close Preview", use_container_width=True):
                        st.session_state["view_target"] = None
                        st.rerun()

            show_pdf_dialog()

        st.write(f"Total Saved Forms: **{len(saved_dict)}**")

        h_col1, h_col2, h_col3, h_col4 = st.columns([1, 2, 3, 4])
        h_col1.markdown("<span style='font-size:14px;'><b>Sr. No.</b></span>", unsafe_allow_html=True)
        h_col2.markdown("<span style='font-size:14px;'><b>Claim ID</b></span>", unsafe_allow_html=True)
        h_col3.markdown("<span style='font-size:14px;'><b>Patient Name</b></span>", unsafe_allow_html=True)
        h_col4.markdown("<span style='font-size:14px;'><b>Actions</b></span>", unsafe_allow_html=True)
        st.divider()

        for idx, (c_id, data) in enumerate(list(saved_dict.items()), 1):
            r_col1, r_col2, r_col3, r_col4 = st.columns([1, 2, 3, 4])
            
            r_col1.markdown(f"<span style='font-size:14px;'>{idx}</span>", unsafe_allow_html=True)
            r_col2.markdown(f"<span style='font-size:14px;'><b>{c_id}</b></span>", unsafe_allow_html=True)
            r_col3.markdown(f"<span style='font-size:14px;'>{data['patient_name'] if data['patient_name'] else '-'}</span>", unsafe_allow_html=True)

            a1, a2, a3 = r_col4.columns(3)

            if a1.button("👁️ View/Print", key=f"vp_{c_id}"):
                st.session_state["view_target"] = c_id
                st.rerun()

            pdf_data = generate_pdf_bytes(data)
            a2.download_button(
                label="📥 PDF",
                data=pdf_data,
                file_name=f"ECHS_Form_{c_id}.pdf",
                mime="application/pdf",
                key=f"dl_{c_id}"
            )

            if a3.button("🗑️ Delete", key=f"d_{c_id}"):
                st.session_state["delete_target"] = c_id
                st.rerun()