import streamlit as st
import streamlit as st
import cloudinary
import cloudinary.api
import cloudinary.uploader
import io
import datetime
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), img.width, img.height

def upload_to_cloudinary(image_bytes, filename):
def upload_to_cloudinary(image_bytes, filename, receipt_data):
    """
    อัพโหลดขึ้น Cloudinary โดยเก็บรวมไว้ในโฟลเดอร์ branch โฟลเดอร์เดียวทั้งหมด
    """
        public_id=filename,
        resource_type="image",
        overwrite=False,
        tags=["receipt_sync_pending"],
        context=receipt_data,
    )
    secure_url = result.get("secure_url", "")
    if not secure_url:
    if not result.get("secure_url") or not result.get("public_id"):
        raise RuntimeError("Cloudinary อัปโหลดสำเร็จแต่ไม่ได้คืนลิงก์รูป")
    return secure_url
    return result


def sync_receipt_from_cloudinary(public_id, asset=None):
    """เขียนรูปที่ติดแท็ก pending กลับเข้า Sheet แล้วปิดงานเมื่อครบทั้งสองฝั่ง."""
    asset = asset or cloudinary.api.resource(public_id, resource_type="image", context=True)
    data = asset.get("context", {}).get("custom", {})
    if not data:
        # upload response อาจไม่คืน context จึงอ่านข้อมูลจริงจาก Admin API อีกครั้ง
        asset = cloudinary.api.resource(public_id, resource_type="image", context=True)
        data = asset.get("context", {}).get("custom", {})
    required = ("reporter", "branch", "zone", "status", "reason", "filename")
    missing = [key for key in required if key not in data]
    if missing:
        return False, f"รูปไม่มีข้อมูลสำรอง: {', '.join(missing)}"

    sheet_ok, sheet_err = log_to_sheet(
        reporter=data["reporter"], branch=data["branch"], zone=data["zone"],
        status=data["status"], reason=data["reason"],
        filename=data["filename"], url="",
    )
    if not sheet_ok:
        return False, sheet_err

    pending_ok, pending_err = update_receipt_sync(data["filename"], sync_status="PENDING")
    if not pending_ok:
        return False, pending_err

    done_ok, done_err = update_receipt_sync(
        data["filename"], url=asset.get("secure_url", ""), sync_status="DONE"
    )
    if not done_ok:
        return False, done_err

    cloudinary.uploader.remove_tag("receipt_sync_pending", [public_id], resource_type="image")
    return True, ""

