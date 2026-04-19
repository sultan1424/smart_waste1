"""
Email notification service using Resend.
"""
import os
import resend
from datetime import datetime

resend.api_key = os.getenv("RESEND_API_KEY")

FROM_EMAIL = "WasteEnergy <onboarding@resend.dev>"
TEST_EMAIL = "alatawisultan14@gmail.com"

def send_bin_critical_restaurant(to_email: str, bin_id: str, fill_pct: float, location: str):
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": TEST_EMAIL,
        "subject": f"🚨 Bin {bin_id} is Critical — {fill_pct:.0f}% Full",
        "html": f"""
        <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#fff;">
            <div style="background:#fee2e2;border-radius:12px;padding:24px;margin-bottom:24px;">
                <h2 style="color:#dc2626;margin:0 0 8px;">⚠️ Critical Bin Alert</h2>
                <p style="color:#7f1d1d;margin:0;font-size:14px;">Immediate action required</p>
            </div>
            <p style="font-size:15px;color:#111827;">Your bin <strong>{bin_id}</strong> at <strong>{location}</strong> has reached <strong style="color:#dc2626;">{fill_pct:.0f}%</strong> capacity.</p>
            <p style="font-size:14px;color:#6b7280;">A pickup has been flagged. Please avoid adding more waste until collected.</p>
            <div style="background:#f9fafb;border-radius:8px;padding:16px;margin-top:24px;">
                <p style="font-size:12px;color:#9ca3af;margin:0;">WasteEnergy Operations · {datetime.now().strftime("%B %d, %Y %H:%M")}</p>
            </div>
        </div>
        """,
    })

def send_bin_critical_collector(to_email: str, bin_id: str, fill_pct: float, location: str):
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": TEST_EMAIL,
        "subject": f"🚛 Urgent Pickup Needed — {bin_id} at {fill_pct:.0f}%",
        "html": f"""
        <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#fff;">
            <div style="background:#fef3c7;border-radius:12px;padding:24px;margin-bottom:24px;">
                <h2 style="color:#d97706;margin:0 0 8px;">🚛 Urgent Pickup Required</h2>
                <p style="color:#78350f;margin:0;font-size:14px;">Bin requires immediate collection</p>
            </div>
            <p style="font-size:15px;color:#111827;">Bin <strong>{bin_id}</strong> at <strong>{location}</strong> has reached <strong style="color:#dc2626;">{fill_pct:.0f}%</strong> capacity.</p>
            <p style="font-size:14px;color:#6b7280;">Please include this bin in your next pickup route.</p>
            <div style="background:#f9fafb;border-radius:8px;padding:16px;margin-top:24px;">
                <p style="font-size:12px;color:#9ca3af;margin:0;">WasteEnergy Operations · {datetime.now().strftime("%B %d, %Y %H:%M")}</p>
            </div>
        </div>
        """,
    })

def send_route_ready_collector(to_email: str, bins_served: int, total_dist_km: float, total_time_hr: float, stop_sequence: list):
    stops_html = "".join([
        f'<li style="padding:6px 0;color:#374151;font-size:14px;">{s}</li>'
        for s in stop_sequence if s != "DEPOT"
    ])
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": TEST_EMAIL,
        "subject": f"🗺️ Route Ready — {bins_served} Bins · {total_dist_km} km",
        "html": f"""
        <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#fff;">
            <div style="background:#eef2ff;border-radius:12px;padding:24px;margin-bottom:24px;">
                <h2 style="color:#3b5bdb;margin:0 0 8px;">🗺️ Optimized Route Ready</h2>
                <p style="color:#3730a3;margin:0;font-size:14px;">Your pickup route has been generated</p>
            </div>
            <div style="display:flex;gap:16px;margin-bottom:24px;">
                <div style="flex:1;background:#f9fafb;border-radius:8px;padding:16px;text-align:center;">
                    <p style="font-size:24px;font-weight:700;color:#111827;margin:0;">{bins_served}</p>
                    <p style="font-size:12px;color:#6b7280;margin:4px 0 0;">Bins to collect</p>
                </div>
                <div style="flex:1;background:#f9fafb;border-radius:8px;padding:16px;text-align:center;">
                    <p style="font-size:24px;font-weight:700;color:#111827;margin:0;">{total_dist_km} km</p>
                    <p style="font-size:12px;color:#6b7280;margin:4px 0 0;">Total distance</p>
                </div>
                <div style="flex:1;background:#f9fafb;border-radius:8px;padding:16px;text-align:center;">
                    <p style="font-size:24px;font-weight:700;color:#111827;margin:0;">{total_time_hr} h</p>
                    <p style="font-size:12px;color:#6b7280;margin:4px 0 0;">Estimated time</p>
                </div>
            </div>
            <h3 style="font-size:14px;font-weight:600;color:#111827;margin-bottom:8px;">Stop Sequence:</h3>
            <ol style="margin:0;padding-left:20px;">{stops_html}</ol>
            <div style="background:#f9fafb;border-radius:8px;padding:16px;margin-top:24px;">
                <p style="font-size:12px;color:#9ca3af;margin:0;">WasteEnergy Operations · {datetime.now().strftime("%B %d, %Y %H:%M")}</p>
            </div>
        </div>
        """,
    })