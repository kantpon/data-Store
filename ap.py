def show_success_dialog():
                    fname = f"{safe_sender}_{ts_file}_{idx+1}_{receipt_id[:12]}"
                    sheet_filename = f"{fname}.jpg"

                    # สร้างข้อมูลก่อนเสมอ: ถ้า Sheet ไม่พร้อม จะยังไม่อัปโหลดรูป
                    sheet_ok, sheet_err = log_to_sheet(
                        reporter=reporter_name.strip(),
                        branch=sender_name.strip(),
                        zone=zone.strip(),
                        status=status_label,
                        reason=incomplete_reason.strip(),
                        filename=sheet_filename,
                        url="",
                    )
                    # อัปโหลดรูปพร้อมข้อมูลสำรองก่อน เพื่อรักษารูปไว้แม้ Sheet ขัดข้อง
                    receipt_data = {
                        "receipt_id": receipt_id,
                        "reporter": reporter_name.strip(),
                        "branch": sender_name.strip(),
                        "zone": zone.strip(),
                        "status": status_label,
                        "reason": incomplete_reason.strip() or "-",
                        "filename": sheet_filename,
                    }
                    upload_result = upload_to_cloudinary(img_bytes, fname, receipt_data)

                    if not sheet_ok:
                    # พยายาม sync ทันที; ถ้าไม่ผ่าน รูปจะคงแท็ก receipt_sync_pending
                    # และจะถูกลอง sync ใหม่เมื่อมีคนเปิดแอปครั้งถัดไป
                    sync_ok, sync_err = sync_receipt_from_cloudinary(
                        upload_result["public_id"], upload_result
                    )
                    if sync_ok:
                        results.append({
                            "filename": fname,
                            "ok": False,
                            "detail": f"บันทึกลง Google Sheet ไม่สำเร็จ: {sheet_err}",
                            "ok": True,
                            "size_kb": round(len(img_bytes) / 1024),
                            "dim": f"{new_w}×{new_h}",
                        })
                    else:
                        # O=PENDING ก่อนเริ่มอัปโหลด เพื่อให้ตามงานที่ค้างได้จากชีต
                        pending_ok, pending_err = update_receipt_sync(
                            sheet_filename, sync_status="PENDING"
                        print(
                            f"PENDING RECEIPT: {upload_result['public_id']} -> {sync_err}"
                        )
                        if not pending_ok:
                            print(
                                f"SYNC STATUS REQUIRED: filename={sheet_filename}, "
                                f"error={pending_err}"
                            )
                            results.append({
                                "filename": fname,
                                "ok": False,
                                "detail": f"ตั้งสถานะ SyncQueue ไม่สำเร็จ: {pending_err}",
                            })
                        else:
                            try:
                                secure_url = upload_to_cloudinary(img_bytes, fname)
                            except Exception as upload_err:
                                update_receipt_sync(
                                    sheet_filename, sync_status="UPLOAD_FAILED"
                                )
                                results.append({
                                    "filename": fname,
                                    "ok": False,
                                    "detail": f"อัปโหลดรูปไม่สำเร็จ: {upload_err}",
                                })
                            else:
                                done_ok, done_err = update_receipt_sync(
                                    sheet_filename,
                                    url=secure_url,
                                    sync_status="DONE",
                                )
                                if done_ok:
                                    results.append({
                                        "filename": fname,
                                        "ok": True,
                                        "size_kb": round(len(img_bytes) / 1024),
                                        "dim": f"{new_w}×{new_h}",
                                    })
                                else:
                                    # รูปและแถวมีอยู่แล้ว แต่ SyncQueue ยังค้าง PENDING
                                    # ผู้ดูแลค้นหา PENDING ในคอลัมน์ O เพื่อตามรายการนี้ได้
                                    print(
                                        f"IMAGE URL SYNC REQUIRED: filename={sheet_filename}, "
                                        f"url={secure_url}, error={done_err}"
                                    )
                                    results.append({
                                        "filename": fname,
                                        "ok": False,
                                        "detail": f"อัปโหลดรูปสำเร็จ แต่เติมลิงก์/SyncQueue ไม่สำเร็จ: {done_err}",
                                    })
                        results.append({
                            "filename": fname,
                            "ok": False,
                            "detail": f"เก็บรูปแล้ว แต่ sync Google Sheet ยังไม่สำเร็จ: {sync_err}",
                        })
                except Exception as e:
                    results.append({"filename": f.name, "ok": False, "detail": str(e)})


                st.markdown(
                    f'<div class="error-box"><strong>❌ ไม่สำเร็จ {len(fail)} รูป โปรดลองอัพโหลดใหม่อีกครั้ง</strong>'
                    f'<br>(ตรวจสอบรายการค้างได้จากคอลัมน์ SyncQueue: PENDING หรือ UPLOAD_FAILED)</div>',
                    f'<br>(หาก Google Sheet ขัดข้องหลังอัปโหลด รูปจะถูกเก็บไว้และระบบจะลอง sync ใหม่อัตโนมัติ)</div>',
                    unsafe_allow_html=True,
                )
