import streamlit as st
import cloudinary
import cloudinary.uploader
import io
import datetime
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image, ImageOps

st.set_page_config(page_title="อัพโหลดใบเสร็จ", page_icon="🧾", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Sarabun', sans-serif; }
    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
    .block-container { background: white; border-radius: 20px; padding: 2.5rem 2rem !important; margin-top: 2rem; box-shadow: 0 20px 60px rgba(0,0,0,0.15); max-width: 680px; }
    h1 { color: #1a1a2e !important; font-weight: 700 !important; text-align: center; }
    .subtitle { text-align: center; color: #6b7280; margin-top: -0.5rem; margin-bottom: 1.5rem; font-size: 1rem; }
    .stButton > button { background: linear-gradient(135deg, #667eea, #764ba2) !important; color: white !important; border: none !important; border-radius: 12px !important; padding: 0.75rem 2rem !important; font-size: 1.1rem !important; font-weight: 600 !important; width: 100%; }
    .success-box { background: #f0fdf4; border: 2px solid #86efac; border-radius: 14px; padding: 1.2rem 1.5rem; color: #166534; margin-top: 1rem; }
    .error-box { background: #fef2f2; border: 2px solid #fca5a5; border-radius: 14px; padding: 1.2rem 1.5rem; color: #991b1b; margin-top: 1rem; }
    .divider { border: none; border-top: 1.5px solid #f3f4f6; margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def setup_cloudinary():
    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"],
        secure=True
    )

@st.cache_resource
def setup_gsheet_client():
    """
    เชื่อมต่อไปยัง Google Spreadsheet (ทั้งไฟล์) ผ่าน Service Account
    ต้องมี st.secrets["gcp_service_account"] และ st.secrets["gsheet"]["sheet_url"]
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["gsheet"]["sheet_url"])

def setup_gsheet():
    """คืนแท็บสำหรับบันทึกข้อมูลใบเสร็จ (default ชื่อ 'receipts')"""
    sheet = setup_gsheet_client()
    return sheet.worksheet(st.secrets["gsheet"].get("worksheet_name", "receipts"))

@st.cache_data(ttl=300, show_spinner=False)
def load_reference_lists():
    """
    ดึงรายชื่อสาขา/โซน จากแท็บอ้างอิง (default ชื่อ 'รายชื่อสาขา') ในไฟล์เดียวกัน
    คอลัมน์ A = สาขา, คอลัมน์ B = โซน (แถวแรกเป็นหัวตาราง)
    ถ้าหาแท็บนี้ไม่เจอ หรือเชื่อมต่อไม่ได้ จะคืนลิสต์ว่างเงียบๆ (ไม่ error ให้ผู้ใช้เห็น)
    """
    try:
        sheet = setup_gsheet_client()
        ref_name = st.secrets["gsheet"].get("reference_worksheet_name", "รายชื่อสาขา")
        ref_ws = sheet.worksheet(ref_name)
        rows = ref_ws.get_all_values()
        rows = rows[1:] if len(rows) > 1 else []  # ข้ามแถวหัวตาราง

        branches = sorted({r[0].strip() for r in rows if len(r) > 0 and r[0].strip()})
        zones = sorted({r[1].strip() for r in rows if len(r) > 1 and r[1].strip()})
        return branches, zones
    except Exception:
        return [], []

def log_to_sheet(branch, zone, status, reason="", filename="", url=""):
    """
    บันทึกแถวข้อมูลลง Google Sheet
    คืน True ถ้าสำเร็จ, False ถ้าไม่สำเร็จ (พร้อม error message ที่ระบุสาเหตุชัดเจน)
    """
    try:
        worksheet = setup_gsheet()
        ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        worksheet.append_row([ts, branch, zone, status, reason, filename, url])
        return True, ""
    except gspread.exceptions.WorksheetNotFound:
        wanted = st.secrets.get("gsheet", {}).get("worksheet_name", "receipts")
        return False, f"[WorksheetNotFound] ไม่พบแท็บชื่อ '{wanted}' ในชีต — ไปเช็คชื่อแท็บด้านล่างของ Google Sheet ให้ตรงกับ worksheet_name ใน secrets"
    except gspread.exceptions.SpreadsheetNotFound:
        return False, "[SpreadsheetNotFound] ไม่พบ Google Sheet ตาม sheet_url ที่ตั้งไว้ — เช็คว่าลิงก์ถูกต้องและยังมีอยู่จริง"
    except gspread.exceptions.APIError as e:
        msg = str(e)
        if "PERMISSION_DENIED" in msg or "403" in msg:
            return False, f"[PermissionDenied] Service Account ยังไม่มีสิทธิ์เข้าถึงชีตนี้ — ไปที่ Google Sheet กด Share แล้วใส่อีเมลจาก client_email ให้เป็น Editor. รายละเอียด: {msg}"
        return False, f"[Google API Error] {msg}"
    except KeyError as e:
        return False, f"[KeyError] ยังไม่มีค่าที่ต้องใช้ใน secrets.toml: {e} — เช็คว่ามีกลุ่ม [gcp_service_account] และ [gsheet] ครบไหม"
    except Exception as e:
        return False, f"[{type(e).__name__}] {str(e)}"

def fix_orientation(file, thumb_side: int = 500, extra_rotation: int = 0):
    """เปิดรูป หมุนตาม EXIF ให้ถูกทาง + หมุนเพิ่มตามที่ผู้ใช้กดปุ่ม แล้วย่อเป็นรูปเล็กสำหรับพรีวิว (โหลดเร็ว)"""
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)
    if extra_rotation:
        img = img.rotate(-extra_rotation, expand=True)
    img.thumbnail((thumb_side, thumb_side), Image.LANCZOS)
    return img

def compress_image(file, max_side: int = 1280, quality: int = 78, extra_rotation: int = 0) -> tuple[bytes, int, int]:
    """
    ลดขนาดรูปให้ด้านยาวไม่เกิน max_side px แล้ว compress เป็น JPEG
    คืน (bytes, new_width, new_height)
    """
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)  # หมุนรูปให้ตรงทิศทางจริงตาม EXIF ก่อน compress
    if extra_rotation:
        img = img.rotate(-extra_rotation, expand=True)  # หมุนเพิ่มตามที่ผู้ใช้กดปุ่ม
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), img.width, img.height

def upload_to_cloudinary(image_bytes, filename):
    """
    อัพโหลดขึ้น Cloudinary โดยเก็บรวมไว้ในโฟลเดอร์ branch โฟลเดอร์เดียวทั้งหมด
    """
    result = cloudinary.uploader.upload(
        image_bytes,
        folder="branch",
        public_id=filename,
        resource_type="image",
        overwrite=False,
    )
    return result.get("secure_url", "")

setup_cloudinary()

if "form_version" not in st.session_state:
    st.session_state.form_version = 0
fv = st.session_state.form_version  # ใช้ต่อท้าย key ของแต่ละช่อง เพื่อรีเซ็ตฟอร์มได้หลังส่งสำเร็จ

st.markdown("# 🧾 อัพโหลดใบเสร็จ")
st.markdown('<p class="subtitle">รูปจะถูกส่งเข้า Cloudinary โดยตรง · ปลอดภัย</p>', unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

if st.session_state.get("flash"):
    st.markdown(st.session_state.flash, unsafe_allow_html=True)
    del st.session_state["flash"]
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

st.markdown("#### 📋 จำนวนใบเสร็จในรูป")
mode = st.radio("โหมด", [ "2 ใบเสร็จ"], label_visibility="collapsed")
num_receipts = int(mode[0])

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 👤 ชื่อสาขาCJ")

branch_list, zone_list = load_reference_lists()
CUSTOM_OPTION = "✏️ พิมพ์ชื่อเอง (ไม่มีในลิสต์)"

if branch_list:
    branch_choice = st.selectbox(
        "ชื่อสาขาCJ",
        [CUSTOM_OPTION] + branch_list,
        label_visibility="collapsed",
        key=f"branch_select_{fv}",
    )
    if branch_choice == CUSTOM_OPTION:
        sender_name = st.text_input(
            "พิมพ์ชื่อสาขาเอง",
            placeholder="เช่น สาขา สามแยกบางกอก",
            label_visibility="collapsed",
            key=f"sender_name_{fv}",
        )
    else:
        sender_name = branch_choice
else:
    # ยังไม่มีลิสต์อ้างอิง (หรือดึงไม่สำเร็จ) -> ใช้ช่องพิมพ์ปกติเหมือนเดิม
    sender_name = st.text_input("ชื่อสาขาCJ", placeholder="เช่น สาขา สามแยกบางกอก", label_visibility="collapsed", key=f"sender_name_{fv}")

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### Zone")

if zone_list:
    zone_choice = st.selectbox(
        "Zone",
        [CUSTOM_OPTION] + zone_list,
        label_visibility="collapsed",
        key=f"zone_select_{fv}",
    )
    if zone_choice == CUSTOM_OPTION:
        zone = st.text_input(
            "พิมพ์ Zone เอง",
            placeholder="เช่น BN BG",
            label_visibility="collapsed",
            key=f"zone_{fv}",
        )
    else:
        zone = zone_choice
else:
    zone = st.text_input("Zone", placeholder="เช่น BN BG", label_visibility="collapsed", key=f"zone_{fv}")

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 🏪 สถานะร้าน")
shop_status = st.radio(
    "สถานะร้าน",
    ["ร้านเปิด (ส่งรูปใบเสร็จ)", "ร้านปิด (ไม่มีรูป)"],
    label_visibility="collapsed",
    key=f"shop_status_{fv}",
)
shop_closed = shop_status == "ร้านปิด (ไม่มีรูป)"

completeness = ""
incomplete_reason = ""
closed_reason = ""

if shop_closed:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("#### 📝 เหตุผลที่ร้านปิด")
    closed_reason = st.text_input(
        "เหตุผลที่ร้านปิด",
        placeholder="เช่น ร้านปิดปรับปรุง, เครื่องเสีย, ไม่พบร้าน, อื่นๆ",
        label_visibility="collapsed",
        key=f"closed_reason_{fv}",
    )

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    missing = []
    if not sender_name.strip():
        missing.append("ชื่อสาขาCJ")
    if not zone.strip():
        missing.append("Zone")
    if not closed_reason.strip():
        missing.append("เหตุผลที่ร้านปิด")

    if st.button("📨 ส่งข้อมูล (ไม่มีรูป)"):
        if missing:
            items = "".join([f"<br>• {m}" for m in missing])
            st.markdown(f'<div class="error-box">⚠️ กรุณากรอกข้อมูลให้ครบก่อนส่ง:{items}</div>', unsafe_allow_html=True)
        else:
            ok, err = log_to_sheet(
                branch=sender_name.strip(),
                zone=zone.strip(),
                status="ร้านปิด",
                reason=closed_reason.strip(),
            )
            ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            if ok:
                st.session_state.flash = (
                    f'<div class="success-box">'
                    f'<strong>✅ บันทึกข้อมูลสำเร็จ!</strong><br>'
                    f'🏪 สาขา: {sender_name.strip()}<br>'
                    f'📍 Zone: {zone.strip()}<br>'
                    f'📝 เหตุผล: {closed_reason.strip()}<br>'
                    f'🕒 เวลา: {ts}'
                    f'</div>'
                )
                st.session_state.form_version += 1
                st.session_state.rotations = {}
                st.rerun()
            else:
                st.markdown(f'<div class="error-box">❌ บันทึกลง Google Sheet ไม่สำเร็จ: {err}</div>', unsafe_allow_html=True)

else:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("#### 📦 เก็บบิลครบไหม")
    completeness = st.selectbox(
        "เก็บบิลครบไหม",
        ["-- กรุณาเลือก --", "ครบ", "ไม่ครบ"],
        label_visibility="collapsed",
        key=f"completeness_{fv}",
    )

    if completeness == "ไม่ครบ":
        incomplete_reason = st.text_input(
            "เหตุผลที่เก็บไม่ครบ",
            placeholder="เช่น เครื่องเสีย, ร้านไม่เปิด, อื่นๆ",
            key=f"incomplete_reason_{fv}",
        )

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("#### 📷 เลือกรูปภาพ (เลือกได้หลายรูปพร้อมกัน)")
    st.caption("💡 กด Ctrl ค้างไว้แล้วคลิกเลือกหลายรูปพร้อมกัน")

    uploaded_files = st.file_uploader(
        "เลือกไฟล์",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key=f"file_uploader_{fv}",
    )

    if uploaded_files:
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown(f"#### 🔍 รูปที่เลือก ({len(uploaded_files)} รูป)")

        if "rotations" not in st.session_state:
            st.session_state.rotations = {}

        cols = st.columns(3)
        for i, f in enumerate(uploaded_files):
            rot_key = f"{f.name}_{f.size}_{i}"
            with cols[i % 3]:
                current_rot = st.session_state.rotations.get(rot_key, 0)
                preview_img = fix_orientation(f, extra_rotation=current_rot)
                st.image(preview_img, caption=f.name, use_container_width=True)
                if st.button("🔄 หมุน 90°", key=f"rotate_{rot_key}"):
                    st.session_state.rotations[rot_key] = (current_rot + 90) % 360
                    st.rerun()

        st.info(f"จะบันทึกในโฟลเดอร์ branch ทั้ง {len(uploaded_files)} รูป")
        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        if st.button(f"☁️ อัพโหลดทั้งหมด ({len(uploaded_files)} รูป)"):
            missing = []
            if not sender_name.strip():
                missing.append("ชื่อสาขาCJ")
            if not zone.strip():
                missing.append("Zone")
            if completeness == "-- กรุณาเลือก --":
                missing.append("เก็บบิลครบไหม")
            if completeness == "ไม่ครบ" and not incomplete_reason.strip():
                missing.append("เหตุผลที่เก็บไม่ครบ")

            if missing:
                items = "".join([f"<br>• {m}" for m in missing])
                st.markdown(f'<div class="error-box">⚠️ กรุณากรอกข้อมูลให้ครบก่อนอัพโหลด:{items}</div>', unsafe_allow_html=True)
            else:
                safe_sender = sender_name.strip().replace("/", "-").replace("\\", "-")
                results = []
                prog = st.progress(0, text="กำลังอัพโหลด...")

                for idx, f in enumerate(uploaded_files):
                    try:
                        # ── compress: max 1280px ด้านยาว, quality 78 + หมุนตามที่ผู้ใช้เลือก ──
                        f.seek(0)  # รีเซ็ตตำแหน่งไฟล์ เพราะพรีวิวด้านบนอ่านไปแล้ว
                        rot_key = f"{f.name}_{f.size}_{idx}"
                        extra_rot = st.session_state.get("rotations", {}).get(rot_key, 0)
                        img_bytes, new_w, new_h = compress_image(f, max_side=1280, quality=78, extra_rotation=extra_rot)

                        ts_file = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        fname = f"{safe_sender}_{ts_file}_{idx+1}"
                        secure_url = upload_to_cloudinary(img_bytes, fname)

                        status_label = "ครบ" if completeness == "ครบ" else "ไม่ครบ"
                        log_ok, log_err = log_to_sheet(
                            branch=sender_name.strip(),
                            zone=zone.strip(),
                            status=status_label,
                            reason=incomplete_reason.strip(),
                            filename=f"{fname}.jpg",
                            url=secure_url,
                        )

                        results.append({
                            "filename": fname,
                            "ok": True,
                            "size_kb": round(len(img_bytes) / 1024),
                            "dim": f"{new_w}×{new_h}",
                            "log_ok": log_ok,
                            "log_err": log_err,
                        })
                    except Exception as e:
                        results.append({"filename": f.name, "ok": False, "err": str(e)})

                    prog.progress((idx+1)/len(uploaded_files), text=f"อัพโหลด {idx+1}/{len(uploaded_files)}...")

                prog.empty()
                ok   = [r for r in results if r["ok"]]
                fail = [r for r in results if not r["ok"]]

                if ok:
                    lines = [f"<strong>✅ อัพโหลดสำเร็จ {len(ok)} รูป!</strong>"]
                    for r in ok:
                        lines.append(f"📄 {r['filename']}.jpg &nbsp;·&nbsp; {r['dim']} px &nbsp;·&nbsp; {r['size_kb']} KB")
                    success_html = f'<div class="success-box">{"<br>".join(lines)}</div>'

                    sheet_fail = [r for r in ok if not r.get("log_ok", True)]
                    sheet_fail_html = ""
                    if sheet_fail:
                        lines2 = ["<strong>⚠️ อัพโหลดรูปสำเร็จ แต่บันทึกลง Google Sheet ไม่สำเร็จ:</strong>"]
                        lines2 += [f"• {r['filename']}: {r.get('log_err','')}" for r in sheet_fail]
                        sheet_fail_html = f'<div class="error-box">{"<br>".join(lines2)}</div>'

                    if not fail:
                        # ทุกรูปอัพโหลดสำเร็จหมด -> ล้างฟอร์มทั้งหมดให้พร้อมกรอกรอบใหม่
                        st.session_state.flash = success_html + sheet_fail_html
                        st.session_state.form_version += 1
                        st.session_state.rotations = {}
                        st.rerun()
                    else:
                        st.markdown(success_html, unsafe_allow_html=True)
                        if sheet_fail_html:
                            st.markdown(sheet_fail_html, unsafe_allow_html=True)
                if fail:
                    lines = [f"<strong>❌ ไม่สำเร็จ {len(fail)} รูป</strong>"]
                    lines += [f"• {r['filename']}: {r.get('err','')}" for r in fail]
                    st.markdown(f'<div class="error-box">{"<br>".join(lines)}</div>', unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;color:#d1d5db;font-size:0.8rem;">รูปทั้งหมดจะถูกส่งเข้าบัญชี Cloudinary ของเจ้าของระบบเท่านั้น</p>', unsafe_allow_html=True)
