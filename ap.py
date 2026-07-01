import streamlit as st
import cloudinary
import cloudinary.uploader
import io
import datetime
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

def fix_orientation(file, thumb_side: int = 500):
    """เปิดรูป หมุนตาม EXIF ให้ถูกทาง แล้วย่อเป็นรูปเล็กสำหรับพรีวิว (โหลดเร็ว)"""
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)
    img.thumbnail((thumb_side, thumb_side), Image.LANCZOS)
    return img

def compress_image(file, max_side: int = 1280, quality: int = 78) -> tuple[bytes, int, int]:
    """
    ลดขนาดรูปให้ด้านยาวไม่เกิน max_side px แล้ว compress เป็น JPEG
    คืน (bytes, new_width, new_height)
    """
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)  # หมุนรูปให้ตรงทิศทางจริงตาม EXIF ก่อน compress
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

st.markdown("# 🧾 อัพโหลดใบเสร็จ")
st.markdown('<p class="subtitle">รูปจะถูกส่งเข้า Cloudinary โดยตรง · ปลอดภัย</p>', unsafe_allow_html=True)
st.markdown('<hr class="divider">', unsafe_allow_html=True)

st.markdown("#### 📋 จำนวนใบเสร็จในรูป")
mode = st.radio("โหมด", [ "2 ใบเสร็จ"], label_visibility="collapsed")
num_receipts = int(mode[0])

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 👤 ชื่อสาขาCJ")
sender_name = st.text_input("ชื่อสาขาCJ", placeholder="เช่น สาขา สามแยกบางกอก", label_visibility="collapsed")

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### Zone")
zone = st.text_input("Zone", placeholder="เช่น BN BG", label_visibility="collapsed")

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("#### 📷 เลือกรูปภาพ (เลือกได้หลายรูปพร้อมกัน)")
st.caption("💡 กด Ctrl ค้างไว้แล้วคลิกเลือกหลายรูปพร้อมกัน")

uploaded_files = st.file_uploader(
    "เลือกไฟล์",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(f"#### 🔍 รูปที่เลือก ({len(uploaded_files)} รูป)")

    cols = st.columns(3)
    for i, f in enumerate(uploaded_files):
        with cols[i % 3]:
            preview_img = fix_orientation(f)
            st.image(preview_img, caption=f.name, use_container_width=True)

    st.info(f"จะบันทึกในโฟลเดอร์ branch ทั้ง {len(uploaded_files)} รูป")
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    if st.button(f"☁️ อัพโหลดทั้งหมด ({len(uploaded_files)} รูป)"):
        if not sender_name.strip():
            st.markdown('<div class="error-box">⚠️ กรุณากรอกชื่อผู้ส่งก่อนอัพโหลด</div>', unsafe_allow_html=True)
        else:
            safe_sender = sender_name.strip().replace("/", "-").replace("\\", "-")
            results = []
            prog = st.progress(0, text="กำลังอัพโหลด...")

            for idx, f in enumerate(uploaded_files):
                try:
                    # ── compress: max 1600px ด้านยาว, quality 82 ──
                    f.seek(0)  # รีเซ็ตตำแหน่งไฟล์ เพราะพรีวิวด้านบนอ่านไปแล้ว
                    img_bytes, new_w, new_h = compress_image(f, max_side=1280, quality=78)

                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    fname = f"{safe_sender}_{ts}_{idx+1}"
                    upload_to_cloudinary(img_bytes, fname)
                    results.append({
                        "filename": fname,
                        "ok": True,
                        "size_kb": round(len(img_bytes) / 1024),
                        "dim": f"{new_w}×{new_h}",
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
                st.markdown(f'<div class="success-box">{"<br>".join(lines)}</div>', unsafe_allow_html=True)
            if fail:
                lines = [f"<strong>❌ ไม่สำเร็จ {len(fail)} รูป</strong>"]
                lines += [f"• {r['filename']}: {r.get('err','')}" for r in fail]
                st.markdown(f'<div class="error-box">{"<br>".join(lines)}</div>', unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;color:#d1d5db;font-size:0.8rem;">รูปทั้งหมดจะถูกส่งเข้าบัญชี Cloudinary ของเจ้าของระบบเท่านั้น</p>', unsafe_allow_html=True)
