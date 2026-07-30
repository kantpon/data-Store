import streamlit as st
import cloudinary
import cloudinary.uploader
import io
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image, ImageOps


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="อัพโหลดใบเสร็จ",
    page_icon="🧾",
    layout="centered"
)


# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Sarabun', sans-serif;
    }

    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
    }

    .block-container {
        background: white;
        border-radius: 20px;
        padding: 2.5rem 2rem !important;
        margin-top: 2rem;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        max-width: 680px;
    }

    h1 {
        color: #1a1a2e !important;
        font-weight: 700 !important;
        text-align: center;
    }

    .subtitle {
        text-align: center;
        color: #6b7280;
        margin-top: -0.5rem;
        margin-bottom: 1.5rem;
        font-size: 1rem;
    }

    .stButton > button {
        background: linear-gradient(135deg, #667eea, #764ba2) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 2rem !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        width: 100%;
    }

    .success-box {
        background: #f0fdf4;
        border: 2px solid #86efac;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        color: #166534;
        margin-top: 1rem;
    }

    .error-box {
        background: #fef2f2;
        border: 2px solid #fca5a5;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        color: #991b1b;
        margin-top: 1rem;
    }

    .warning-box {
        background: #fffbeb;
        border: 2px solid #fcd34d;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        color: #92400e;
        margin-top: 1rem;
    }

    .branch-box {
        background: #eef2ff;
        border: 2px solid #c7d2fe;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        color: #3730a3;
        margin-top: 0.6rem;
    }

    .guide-box {
        background: #fffbeb;
        border: 2px solid #fcd34d;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        color: #92400e;
        margin: 1rem 0;
        line-height: 1.7;
    }

    .divider {
        border: none;
        border-top: 1.5px solid #f3f4f6;
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# CLOUDINARY
# =========================================================

@st.cache_resource
def setup_cloudinary():

    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"],
        secure=True
    )


# =========================================================
# GOOGLE SHEET CLIENT
# =========================================================

@st.cache_resource
def get_gsheet_client():

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes
    )

    return gspread.authorize(creds)


# =========================================================
# GOOGLE SHEET
# =========================================================

def setup_gsheet():

    client = get_gsheet_client()

    sheet = client.open_by_url(
        st.secrets["gsheet"]["sheet_url"]
    )

    worksheet = sheet.worksheet(
        st.secrets["gsheet"].get(
            "worksheet_name",
            "receipts"
        )
    )

    return worksheet


# =========================================================
# LOAD BRANCH LIST
# =========================================================

@st.cache_data(ttl=300)
def load_branch_list():

    try:

        client = get_gsheet_client()

        sheet_url = st.secrets["gsheet"].get(
            "branch_sheet_url",
            st.secrets["gsheet"]["sheet_url"]
        )

        sheet = client.open_by_url(sheet_url)

        ws_name = st.secrets["gsheet"].get(
            "branch_worksheet_name",
            "รายชื่อสาขา"
        )

        worksheet = sheet.worksheet(ws_name)

        records = worksheet.get_all_records()

        branches = []

        for r in records:

            code = str(
                r.get("รหัส", "")
            ).strip()

            name = str(
                r.get("รายชื่อสาขา", "")
            ).strip()

            zone = str(
                r.get("zone", "")
            ).strip()

            if name:

                branches.append({
                    "code": code,
                    "name": name,
                    "zone": zone
                })

        return branches, ""

    except Exception as e:

        return [], str(e)


# =========================================================
# GOOGLE SHEET LOG
# =========================================================

def log_to_sheet(
    reporter,
    branch,
    zone,
    status,
    reason="",
    filename="",
    url=""
):

    try:

        worksheet = setup_gsheet()

        ts = datetime.datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        )

        worksheet.append_row(
            [
                ts,
                reporter,
                branch,
                zone,
                status,
                reason,
                filename,
                url
            ],
            value_input_option="USER_ENTERED"
        )

        return True, ""

    except Exception as e:

        return False, str(e)


# =========================================================
# RETRY GOOGLE SHEET
# =========================================================

def log_to_sheet_with_retry(
    reporter,
    branch,
    zone,
    status,
    reason="",
    filename="",
    url="",
    max_retries=3
):

    last_error = ""

    for attempt in range(1, max_retries + 1):

        try:

            success, error = log_to_sheet(
                reporter=reporter,
                branch=branch,
                zone=zone,
                status=status,
                reason=reason,
                filename=filename,
                url=url
            )

            if success:

                return True, "", attempt

            last_error = error

        except Exception as e:

            last_error = str(e)

        # ถ้ายังไม่ใช่รอบสุดท้าย
        if attempt < max_retries:

            time.sleep(2 * attempt)

    return False, last_error, max_retries


# =========================================================
# IMAGE ORIENTATION
# =========================================================

def fix_orientation(
    file,
    thumb_side: int = 500,
    extra_rotation: int = 0
):

    img = Image.open(file)

    img = ImageOps.exif_transpose(img)

    if extra_rotation:

        img = img.rotate(
            -extra_rotation,
            expand=True
        )

    img.thumbnail(
        (thumb_side, thumb_side),
        Image.LANCZOS
    )

    return img


# =========================================================
# COMPRESS IMAGE
# =========================================================

def compress_image(
    file,
    max_side: int = 1280,
    quality: int = 78,
    extra_rotation: int = 0
):

    img = Image.open(file)

    img = ImageOps.exif_transpose(img)

    if extra_rotation:

        img = img.rotate(
            -extra_rotation,
            expand=True
        )

    if img.mode in ("RGBA", "P"):

        img = img.convert("RGB")

    w, h = img.size

    if max(w, h) > max_side:

        scale = max_side / max(w, h)

        img = img.resize(
            (
                int(w * scale),
                int(h * scale)
            ),
            Image.LANCZOS
        )

    buf = io.BytesIO()

    img.save(
        buf,
        format="JPEG",
        quality=quality,
        optimize=True
    )

    return (
        buf.getvalue(),
        img.width,
        img.height
    )


# =========================================================
# UPLOAD CLOUDINARY
# =========================================================

def upload_to_cloudinary(
    image_bytes,
    filename
):

    result = cloudinary.uploader.upload(
        image_bytes,
        folder="branch",
        public_id=filename,
        resource_type="image",
        overwrite=False,
    )

    secure_url = result.get(
        "secure_url",
        ""
    )

    if not secure_url:

        raise Exception(
            "Cloudinary ไม่ได้ส่ง secure_url กลับมา"
        )

    return secure_url


# =========================================================
# INIT
# =========================================================

setup_cloudinary()


if "show_sent_dialog" not in st.session_state:

    st.session_state.show_sent_dialog = False


if "sent_count" not in st.session_state:

    st.session_state.sent_count = 0


# =========================================================
# SUCCESS DIALOG
# =========================================================

@st.dialog("✅ ส่งข้อมูลสำเร็จ")
def show_success_dialog():

    st.markdown("### คุณส่งแล้ว")

    st.write(
        f"อัพโหลดใบเสร็จ "
        f"{st.session_state.sent_count} รูป "
        f"และบันทึกข้อมูลเรียบร้อยแล้ว"
    )

    if st.button(
        "ตกลง",
        use_container_width=True
    ):

        st.session_state.show_sent_dialog = False

        st.rerun()


# =========================================================
# HEADER
# =========================================================

st.markdown(
    "# 🧾 อัพโหลดใบเสร็จ"
)

st.markdown(
    '<p class="subtitle">'
    'รูปจะถูกส่งเข้า Cloudinary โดยตรง · ปลอดภัย'
    '</p>',
    unsafe_allow_html=True
)

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)


# =========================================================
# NUMBER OF RECEIPTS
# =========================================================

st.markdown("#### 📋 จำนวนใบเสร็จในรูป")

mode = st.radio(
    "โหมด",
    ["2 ใบเสร็จ"],
    label_visibility="collapsed"
)

num_receipts = int(mode[0])


# =========================================================
# REPORTER
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown("#### 🙋 ชื่อผู้กรอก")

reporter_name = st.text_input(
    "ชื่อผู้กรอก",
    placeholder="พิมพ์ชื่อผู้กรอกข้อมูล",
    label_visibility="collapsed",
)


# =========================================================
# BRANCH
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown("#### 🏢 เลือกสาขา")


branches, branch_err = load_branch_list()


if branch_err:

    st.markdown(
        f'<div class="error-box">'
        f'❌ โหลดรายชื่อสาขาไม่สำเร็จ: {branch_err}'
        f'<br>ตรวจสอบว่ามี worksheet ชื่อ "รายชื่อสาขา" '
        f'(หรือชื่อที่ตั้งใน secrets) '
        f'และมีคอลัมน์หัวตาราง รหัส, รายชื่อสาขา, zone'
        f'</div>',
        unsafe_allow_html=True
    )

    sender_name, zone = "", ""


elif not branches:

    st.markdown(
        '<div class="error-box">'
        '⚠️ ยังไม่มีรายชื่อสาขาในชีท '
        'กรุณาเพิ่มข้อมูลก่อนใช้งาน'
        '</div>',
        unsafe_allow_html=True
    )

    sender_name, zone = "", ""


else:

    # =====================================================
    # ZONE
    # =====================================================

    st.caption("📍 ขั้นที่ 1: เลือก Zone")

    zone_list = sorted({
        b["zone"]
        for b in branches
        if b["zone"]
    })

    zone_options = [
        "ทั้งหมด (ทุก Zone)"
    ] + zone_list

    picked_zone = st.selectbox(
        "เลือก Zone",
        zone_options,
        label_visibility="collapsed",
    )


    if picked_zone == "ทั้งหมด (ทุก Zone)":

        filtered_branches = branches

    else:

        filtered_branches = [
            b
            for b in branches
            if b["zone"] == picked_zone
        ]


    # =====================================================
    # BRANCH SELECT
    # =====================================================

    def display_label(b):

        if b["code"]:

            return f'{b["code"]} | {b["name"]}'

        return b["name"]


    st.caption(
        f"🔎 ขั้นที่ 2: พิมพ์รหัสหรือชื่อเพื่อค้นหา/เลือกสาขา "
        f"({len(filtered_branches)} สาขา)"
    )

    branch_options = [
        "-- กรุณาเลือกสาขา --"
    ] + [
        display_label(b)
        for b in filtered_branches
    ]

    picked = st.selectbox(
        "เลือกสาขา",
        branch_options,
        label_visibility="collapsed",
        key=f"branch_select_{picked_zone}",
    )


    if picked != "-- กรุณาเลือกสาขา --":

        matched = next(
            (
                b
                for b in filtered_branches
                if display_label(b) == picked
            ),
            None
        )

    else:

        matched = None


    if matched:

        sender_name = matched["name"]

        zone = matched["zone"]

        code_note = (
            f' &nbsp;·&nbsp; รหัส: {matched["code"]}'
            if matched["code"]
            else ""
        )

        st.markdown(
            f'<div class="branch-box">'
            f'🏪 <strong>{matched["name"]}</strong> '
            f'&nbsp;·&nbsp; Zone {matched["zone"] or "-"}'
            f'{code_note}'
            f'</div>',
            unsafe_allow_html=True
        )

    else:

        sender_name, zone = "", ""


# =========================================================
# COMPLETENESS
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown("#### 📦 เครื่องที่ขาด")

st.caption(
    'เลือก "ครบ" หรือเลือกเครื่องที่ขาดได้หลายเครื่อง '
    '(เลือก "ครบ" แล้วจะเลือกเครื่องอื่นไม่ได้)'
)


def _enforce_completeness_exclusive():

    prev = st.session_state.get(
        "_prev_completeness_sel",
        []
    )

    cur = st.session_state.completeness_sel

    added = [
        x
        for x in cur
        if x not in prev
    ]

    if added:

        new_item = added[0]

        if new_item == "ครบ":

            st.session_state.completeness_sel = [
                "ครบ"
            ]

        elif "ครบ" in cur:

            st.session_state.completeness_sel = [
                x
                for x in cur
                if x != "ครบ"
            ]

    st.session_state[
        "_prev_completeness_sel"
    ] = st.session_state.completeness_sel


completeness_sel = st.multiselect(
    "เครื่องที่ขาด",
    [
        "ครบ",
        "ขาดเครื่องที่ 1",
        "ขาดเครื่องที่ 2",
        "ขาดเครื่องที่ 3",
        "ขาดเครื่องที่ 4"
    ],
    label_visibility="collapsed",
    key="completeness_sel",
    on_change=_enforce_completeness_exclusive,
)


if "ครบ" in completeness_sel:

    completeness = "ครบ"

elif completeness_sel:

    completeness = "ไม่ครบ"

else:

    completeness = "-- กรุณาเลือก --"


incomplete_reason = ", ".join(
    [
        x
        for x in completeness_sel
        if x != "ครบ"
    ]
)


# =========================================================
# FILE UPLOAD
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown("#### 📷 เลือกรูปภาพ (เลือกได้หลายรูปพร้อมกัน)")

st.caption(
    "💡 กด Ctrl ค้างไว้แล้วคลิกเลือกหลายรูปพร้อมกัน"
)

uploaded_files = st.file_uploader(
    "เลือกไฟล์",
    type=[
        "jpg",
        "jpeg",
        "png",
        "webp"
    ],
    accept_multiple_files=True,
    label_visibility="collapsed",
)


# =========================================================
# PREVIEW
# =========================================================

if uploaded_files:

    st.markdown(
        '<hr class="divider">',
        unsafe_allow_html=True
    )

    st.markdown(
        f"#### 🔍 ตรวจสอบรูปก่อนส่ง "
        f"({len(uploaded_files)} รูป)"
    )

    st.markdown(
        '<div class="guide-box">'
        '📸 <strong>โปรดถ่ายบิลให้ถูกต้อง</strong>'
        '<br><br>'
        '1. ภาพชัดให้อ่านค่าได้<br>'
        '2. มีระยะห่างจากกันระหว่างบิล<br>'
        '3. ภาพเป็นแนวตั้ง '
        '(หากเป็นแนวนอนสามารถปรับหมุนได้)'
        '<br><br>'
        '</div>',
        unsafe_allow_html=True
    )


    if "rotations" not in st.session_state:

        st.session_state.rotations = {}


    for i, f in enumerate(uploaded_files):

        rot_key = (
            f"{f.name}_{f.size}_{i}"
        )

        current_rot = (
            st.session_state.rotations.get(
                rot_key,
                0
            )
        )

        preview_img = fix_orientation(
            f,
            thumb_side=1000,
            extra_rotation=current_rot
        )

        st.image(
            preview_img,
            caption=f.name,
            use_container_width=True
        )


        c1, c2, c3 = st.columns(3)


        with c1:

            if st.button(
                "↺ หมุนซ้าย",
                key=f"rotate_left_{rot_key}",
                use_container_width=True
            ):

                st.session_state.rotations[
                    rot_key
                ] = (
                    current_rot - 90
                ) % 360

                st.rerun()


        with c2:

            if st.button(
                "↻ หมุนขวา",
                key=f"rotate_right_{rot_key}",
                use_container_width=True
            ):

                st.session_state.rotations[
                    rot_key
                ] = (
                    current_rot + 90
                ) % 360

                st.rerun()


        with c3:

            if st.button(
                "🔃 กลับหัว",
                key=f"rotate_flip_{rot_key}",
                use_container_width=True
            ):

                st.session_state.rotations[
                    rot_key
                ] = (
                    current_rot + 180
                ) % 360

                st.rerun()


        st.markdown(
            '<hr class="divider">',
            unsafe_allow_html=True
        )


    st.info(
        f"จะบันทึกในโฟลเดอร์ branch "
        f"ทั้ง {len(uploaded_files)} รูป"
    )

    st.markdown(
        '<hr class="divider">',
        unsafe_allow_html=True
    )


    # =====================================================
    # UPLOAD BUTTON
    # =====================================================

    if st.button(
        f"☁️ อัพโหลดทั้งหมด ({len(uploaded_files)} รูป)"
    ):

        # =================================================
        # VALIDATE
        # =================================================

        missing = []

        if not reporter_name.strip():

            missing.append(
                "ชื่อผู้กรอก"
            )

        if not sender_name.strip():

            missing.append(
                "สาขา (กรุณาเลือกจากรายการ)"
            )

        if completeness == "-- กรุณาเลือก --":

            missing.append(
                "เครื่องที่ขาด"
            )

        if (
            completeness == "ไม่ครบ"
            and not incomplete_reason.strip()
        ):

            missing.append(
                "เครื่องที่ขาด "
                "(เลือกอย่างน้อย 1 เครื่อง)"
            )


        if missing:

            items = "".join(
                [
                    f"<br>• {m}"
                    for m in missing
                ]
            )

            st.markdown(
                f'<div class="error-box">'
                f'⚠️ กรุณากรอกข้อมูลให้ครบก่อนอัพโหลด:'
                f'{items}'
                f'</div>',
                unsafe_allow_html=True
            )


        else:

            # =============================================
            # START UPLOAD
            # =============================================

            safe_sender = (
                sender_name
                .strip()
                .replace("/", "-")
                .replace("\\", "-")
            )

            results = []

            prog = st.progress(
                0,
                text="กำลังอัพโหลด..."
            )


            # =============================================
            # LOOP FILES
            # =============================================

            for idx, f in enumerate(
                uploaded_files
            ):

                try:

                    # -------------------------------------
                    # RESET FILE
                    # -------------------------------------

                    f.seek(0)


                    # -------------------------------------
                    # ROTATION
                    # -------------------------------------

                    rot_key = (
                        f"{f.name}_{f.size}_{idx}"
                    )

                    extra_rot = (
                        st.session_state
                        .get("rotations", {})
                        .get(
                            rot_key,
                            0
                        )
                    )


                    # -------------------------------------
                    # COMPRESS
                    # -------------------------------------

                    (
                        img_bytes,
                        new_w,
                        new_h
                    ) = compress_image(
                        f,
                        max_side=1280,
                        quality=78,
                        extra_rotation=extra_rot
                    )


                    # -------------------------------------
                    # FILE NAME
                    # -------------------------------------

                    ts_file = (
                        datetime.datetime.now()
                        .strftime(
                            "%Y%m%d_%H%M%S_%f"
                        )
                    )

                    fname = (
                        f"{safe_sender}_"
                        f"{ts_file}_"
                        f"{idx+1}"
                    )


                    # =====================================
                    # CLOUDINARY
                    # =====================================

                    secure_url = (
                        upload_to_cloudinary(
                            img_bytes,
                            fname
                        )
                    )


                    # =====================================
                    # GOOGLE SHEET
                    # =====================================

                    status_label = (
                        "ครบ"
                        if completeness == "ครบ"
                        else "ไม่ครบ"
                    )


                    (
                        log_ok,
                        log_err,
                        retry_count
                    ) = log_to_sheet_with_retry(
                        reporter=reporter_name.strip(),
                        branch=sender_name.strip(),
                        zone=zone.strip(),
                        status=status_label,
                        reason=incomplete_reason.strip(),
                        filename=f"{fname}.jpg",
                        url=secure_url,
                        max_retries=3
                    )


                    # =====================================
                    # RESULT
                    # =====================================

                    results.append({

                        "filename": fname,

                        "cloud_ok": True,

                        "sheet_ok": log_ok,

                        "sheet_retry": retry_count,

                        "size_kb": round(
                            len(img_bytes) / 1024
                        ),

                        "dim": (
                            f"{new_w}×{new_h}"
                        ),

                        "log_err": log_err,

                        "url": secure_url
                    })


                except Exception as e:

                    results.append({

                        "filename": f.name,

                        "cloud_ok": False,

                        "sheet_ok": False,

                        "sheet_retry": 0,

                        "size_kb": 0,

                        "dim": "-",

                        "log_err": "",

                        "err": str(e),

                        "url": ""
                    })


                # =========================================
                # PROGRESS
                # =========================================

                prog.progress(
                    (idx + 1)
                    / len(uploaded_files),
                    text=(
                        f"อัพโหลด "
                        f"{idx + 1}/"
                        f"{len(uploaded_files)}..."
                    )
                )


            prog.empty()


            # =================================================
            # SUMMARY
            # =================================================

            cloud_success = [
                r
                for r in results
                if r.get("cloud_ok")
            ]

            cloud_fail = [
                r
                for r in results
                if not r.get("cloud_ok")
            ]

            sheet_success = [
                r
                for r in results
                if (
                    r.get("cloud_ok")
                    and r.get("sheet_ok")
                )
            ]

            sheet_fail = [
                r
                for r in results
                if (
                    r.get("cloud_ok")
                    and not r.get("sheet_ok")
                )
            ]


            # =================================================
            # CLOUDINARY SUMMARY
            # =================================================

            if cloud_success:

                lines = [
                    "<strong>"
                    f"☁️ Cloudinary สำเร็จ "
                    f"{len(cloud_success)}/"
                    f"{len(uploaded_files)} รูป"
                    "</strong>"
                ]

                for r in cloud_success:

                    lines.append(
                        f"📄 {r['filename']}.jpg"
                        f" · {r['dim']} px"
                        f" · {r['size_kb']} KB"
                    )

                st.markdown(
                    '<div class="success-box">'
                    + "<br>".join(lines)
                    + "</div>",
                    unsafe_allow_html=True
                )


            # =================================================
            # GOOGLE SHEET SUCCESS
            # =================================================

            if sheet_success:

                st.markdown(
                    '<div class="success-box">'
                    f'<strong>📊 Google Sheet สำเร็จ '
                    f'{len(sheet_success)}/'
                    f'{len(uploaded_files)} รายการ</strong>'
                    '</div>',
                    unsafe_allow_html=True
                )


            # =================================================
            # GOOGLE SHEET FAILED
            # =================================================

            if sheet_fail:

                lines = [
                    "<strong>"
                    "⚠️ Cloudinary สำเร็จ "
                    "แต่ Google Sheet ไม่สำเร็จ"
                    "</strong>"
                ]

                for r in sheet_fail:

                    lines.append(
                        f"• {r['filename']}.jpg"
                        f" — ลอง {r['sheet_retry']} ครั้ง"
                        f"<br>&nbsp;&nbsp;"
                        f"Error: {r.get('log_err', '')}"
                    )

                st.markdown(
                    '<div class="error-box">'
                    + "<br>".join(lines)
                    + "</div>",
                    unsafe_allow_html=True
                )


            # =================================================
            # CLOUDINARY FAILED
            # =================================================

            if cloud_fail:

                lines = [
                    "<strong>"
                    f"❌ Cloudinary ไม่สำเร็จ "
                    f"{len(cloud_fail)} รูป"
                    "</strong>"
                ]

                for r in cloud_fail:

                    lines.append(
                        f"• {r['filename']}"
                        f" — {r.get('err', '')}"
                    )

                st.markdown(
                    '<div class="error-box">'
                    + "<br>".join(lines)
                    + "</div>",
                    unsafe_allow_html=True
                )


            # =================================================
            # FINAL STATUS
            # =================================================

            total = len(uploaded_files)

            if (
                len(cloud_success) == total
                and len(sheet_success) == total
            ):

                # ทุกอย่างสำเร็จ

                st.session_state.show_sent_dialog = True

                st.session_state.sent_count = (
                    len(sheet_success)
                )

                st.rerun()


            elif sheet_fail or cloud_fail:

                # มีบางส่วนล้มเหลว

                st.markdown(
                    '<div class="warning-box">'
                    '<strong>⚠️ งานยังไม่สมบูรณ์</strong>'
                    '<br><br>'
                    f'☁️ Cloudinary: '
                    f'{len(cloud_success)}/{total}'
                    '<br>'
                    f'📊 Google Sheet: '
                    f'{len(sheet_success)}/{total}'
                    '<br><br>'
                    'กรุณาตรวจสอบรายการที่มีเครื่องหมาย ❌ '
                    'หรือ ⚠️ ด้านบน'
                    '</div>',
                    unsafe_allow_html=True
                )


# =========================================================
# SUCCESS DIALOG
# =========================================================

if st.session_state.show_sent_dialog:

    show_success_dialog()


# =========================================================
# FOOTER
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown(
    '<p style="text-align:center;'
    'color:#d1d5db;'
    'font-size:0.8rem;">'
    'รูปทั้งหมดจะถูกส่งเข้าบัญชี '
    'Cloudinary ของเจ้าของระบบเท่านั้น'
    '</p>',
    unsafe_allow_html=True
)
