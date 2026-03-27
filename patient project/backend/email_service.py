# backend/email_service.py
import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
from dotenv import load_dotenv

load_dotenv()

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")


# ─────────────────────────────────────────────────────────────
#  ClinIQ HTML Email Template
# ─────────────────────────────────────────────────────────────
def _build_html_email(
    subject: str,
    heading: str,
    body_html: str,
    cta_text: str = None,
    cta_url: str = None,
) -> str:
    cta_block = ""
    if cta_text and cta_url:
        cta_block = f"""
        <tr>
          <td align="center" style="padding: 8px 40px 32px;">
            <a href="{cta_url}"
               style="display:inline-block;padding:12px 32px;background:#C9A96E;color:#0D0D0F;
                      font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:14px;
                      font-weight:600;border-radius:8px;text-decoration:none;letter-spacing:0.01em;">
              {cta_text}
            </a>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#F5F1EA;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F5F1EA;padding:40px 0;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background:#FDFBF7;border-radius:16px;
                      overflow:hidden;box-shadow:0 4px 32px rgba(0,0,0,0.08);">

          <!-- ── Header ── -->
          <tr>
            <td style="background:#FDFBF7;padding:0;border-bottom:3px solid #C9A96E;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <!-- Gold left stripe -->
                  <td width="4" style="background:#C9A96E;">&nbsp;</td>
                  <td style="padding:24px 32px;">
                    <table cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <!-- Logo mark -->
                        <td style="padding-right:12px;">
                          <div style="width:36px;height:36px;background:linear-gradient(140deg,#C9A96E,#A07040);
                                      border-radius:8px;display:inline-flex;align-items:center;
                                      justify-content:center;text-align:center;line-height:36px;">
                            <!-- Plus icon approximated with text for email clients -->
                            <span style="color:#FDFBF7;font-size:22px;font-weight:300;line-height:1;">✚</span>
                          </div>
                        </td>
                        <!-- Brand name -->
                        <td style="vertical-align:middle;">
                          <span style="font-size:20px;font-weight:700;color:#1A1714;letter-spacing:-0.01em;">Clin</span><span
                            style="font-size:20px;font-weight:700;color:#C9A96E;letter-spacing:-0.01em;">IQ</span>
                          <div style="font-size:10px;color:#9E948A;margin-top:1px;letter-spacing:0.04em;">
                            The intelligence your clinic never had.
                          </div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── Heading band ── -->
          <tr>
            <td style="background:#F5F1EA;padding:28px 40px 20px;">
              <p style="margin:0;font-size:11px;font-weight:600;color:#A07040;
                         letter-spacing:0.1em;text-transform:uppercase;">ClinIQ Notification</p>
              <h1 style="margin:8px 0 0;font-size:24px;font-weight:700;color:#1A1714;line-height:1.3;">
                {heading}
              </h1>
            </td>
          </tr>

          <!-- ── Divider ── -->
          <tr>
            <td style="padding:0 40px;">
              <div style="height:1px;background:#E2D9CC;"></div>
            </td>
          </tr>

          <!-- ── Body ── -->
          <tr>
            <td style="padding:28px 40px 24px;font-size:15px;color:#2C2825;line-height:1.7;">
              {body_html}
            </td>
          </tr>

          <!-- ── CTA ── -->
          {cta_block}

          <!-- ── Divider ── -->
          <tr>
            <td style="padding:0 40px;">
              <div style="height:1px;background:#E2D9CC;"></div>
            </td>
          </tr>

          <!-- ── Footer ── -->
          <tr>
            <td style="background:#F0EBE0;padding:24px 40px;border-radius:0 0 16px 16px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-size:11px;color:#9E948A;line-height:1.7;">
                    <strong style="color:#6B635A;">ClinIQ</strong> — AI-assisted medical consultations<br/>
                    This is an automated message. Please do not reply to this email.<br/>
                    <a href="https://patient-project-seven.vercel.app/privacy-policy.html" style="color:#A07040;text-decoration:none;">Privacy Policy</a>
                    &nbsp;·&nbsp;
                    <a href="https://patient-project-seven.vercel.app/terms-of-service.html" style="color:#A07040;text-decoration:none;">Terms of Service</a>
                    &nbsp;·&nbsp;
                    <a href="https://patient-project-seven.vercel.app/help-centre.html" style="color:#A07040;text-decoration:none;">Help Centre</a>
                  </td>
                  <td align="right" style="vertical-align:top;">
                    <span style="font-size:10px;color:#9E948A;">© 2026 ClinIQ</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
        <!-- /Card -->

      </td>
    </tr>
  </table>

</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  Pre-built Email Types
# ─────────────────────────────────────────────────────────────


def _prescription_html(
    patient_name: str,
    doctor_name: str,
    date_str: str,
    notes: str,
    follow_up_days: int = None,
) -> tuple:
    """Returns (heading, body_html) for a prescription email."""
    follow_up_row = ""
    if follow_up_days:
        follow_up_row = f"""
        <tr>
          <td style="padding:10px 0 0;">
            <div style="background:#FAF3E4;border-left:3px solid #C9A96E;border-radius:6px;
                        padding:12px 16px;font-size:13px;color:#A07040;">
              &#9658;&nbsp; <strong>Follow-up required in {follow_up_days} days.</strong>
              Please book your next appointment.
            </div>
          </td>
        </tr>
        """

    notes_formatted = notes.replace("\n", "<br/>")

    body_html = f"""
    <p style="margin:0 0 20px;color:#6B635A;">
      Dear <strong style="color:#1A1714;">{patient_name}</strong>,
    </p>
    <p style="margin:0 0 24px;color:#6B635A;">
      Your consultation with <strong style="color:#1A1714;">Dr. {doctor_name}</strong> on
      <strong style="color:#1A1714;">{date_str}</strong> is complete.
      Your prescription and doctor's notes are attached to this email as a PDF.
    </p>

    <!-- Prescription card -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:#F5F1EA;border:1px solid #E2D9CC;border-left:3px solid #C9A96E;
                  border-radius:10px;margin-bottom:24px;">
      <tr>
        <td style="padding:20px 24px;">
          <p style="margin:0 0 4px;font-size:11px;font-weight:600;color:#A07040;
                     letter-spacing:0.08em;text-transform:uppercase;">Prescription Summary</p>
          <p style="margin:0;font-size:13px;color:#2C2825;line-height:1.8;">{notes_formatted}</p>
        </td>
      </tr>
      <tr><td>{follow_up_row}</td></tr>
    </table>

    <p style="margin:0;font-size:13px;color:#9E948A;">
      The full clinical report including AI triage details is attached as a PDF.
      Keep it for your records and share it with any other healthcare providers as needed.
    </p>
    """
    return "Your Prescription is Ready", body_html


def _appointment_confirmation_html(
    patient_name: str, doctor_name: str, date_str: str, time_str: str
) -> tuple:
    body_html = f"""
    <p style="margin:0 0 20px;color:#6B635A;">
      Dear <strong style="color:#1A1714;">{patient_name}</strong>,
    </p>
    <p style="margin:0 0 24px;color:#6B635A;">
      Your appointment has been successfully booked. Here are your details:
    </p>

    <!-- Appointment card -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background:#F5F1EA;border:1px solid #E2D9CC;border-radius:10px;margin-bottom:24px;">
      <tr>
        <td width="50%" style="padding:16px 20px;border-right:1px solid #E2D9CC;">
          <p style="margin:0 0 4px;font-size:10px;color:#9E948A;text-transform:uppercase;letter-spacing:0.08em;">Doctor</p>
          <p style="margin:0;font-size:15px;font-weight:600;color:#1A1714;">Dr. {doctor_name}</p>
        </td>
        <td width="50%" style="padding:16px 20px;">
          <p style="margin:0 0 4px;font-size:10px;color:#9E948A;text-transform:uppercase;letter-spacing:0.08em;">Date & Time</p>
          <p style="margin:0;font-size:15px;font-weight:600;color:#1A1714;">{date_str} &nbsp;·&nbsp; {time_str}</p>
        </td>
      </tr>
    </table>

    <p style="margin:0;font-size:13px;color:#9E948A;">
      Please arrive a few minutes early. To reschedule or cancel, log in to your ClinIQ dashboard.
    </p>
    """
    return "Appointment Confirmed", body_html


def _welcome_html(patient_name: str) -> tuple:
    body_html = f"""
    <p style="margin:0 0 20px;color:#6B635A;">
      Welcome, <strong style="color:#1A1714;">{patient_name}</strong>!
    </p>
    <p style="margin:0 0 16px;color:#6B635A;">
      Your ClinIQ account is ready. You can now:
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px;">
      {
        "".join(
            [
                f'''
      <tr>
        <td style="padding:6px 0;">
          <span style="color:#C9A96E;font-size:16px;">&#10003;</span>&nbsp;
          <span style="font-size:14px;color:#2C2825;">{item}</span>
        </td>
      </tr>'''
                for item in [
                    "Chat with our AI triage assistant about your symptoms",
                    "Book appointments with verified doctors",
                    "Upload and manage your medical records securely",
                    "Receive AI-generated prescriptions and clinical summaries",
                ]
            ]
        )
    }
    </table>
    <p style="margin:0;font-size:13px;color:#9E948A;">
      Your health data is encrypted and never shared without your consent.
    </p>
    """
    return "Welcome to ClinIQ", body_html


# ─────────────────────────────────────────────────────────────
#  Core Send Function
# ─────────────────────────────────────────────────────────────
def _send(
    to_email: str,
    subject: str,
    html_body: str,
    pdf_bytes: bytes = None,
    pdf_filename: str = None,
) -> bool:
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("Warning: Email credentials not set in .env. Email not sent.")
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"ClinIQ <{SENDER_EMAIL}>"
    msg["To"] = to_email

    # Attach HTML body
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Attach PDF bytes directly — no file path needed, safe on ephemeral filesystems
    if pdf_bytes and pdf_filename:
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{pdf_filename}"')
        msg.attach(part)

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


# ─────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────
def send_prescription_email(
    to_email: str,
    patient_name: str,
    doctor_name: str,
    date_str: str,
    notes: str,
    pdf_bytes: bytes = None,
    pdf_filename: str = None,
    follow_up_days: int = None,
) -> bool:
    heading, body_html = _prescription_html(
        patient_name, doctor_name, date_str, notes, follow_up_days
    )
    subject = f"ClinIQ — Your Prescription from Dr. {doctor_name}"
    html = _build_html_email(subject, heading, body_html)
    return _send(
        to_email, subject, html, pdf_bytes=pdf_bytes, pdf_filename=pdf_filename
    )


def send_appointment_confirmation(
    to_email: str,
    patient_name: str,
    doctor_name: str,
    date_str: str,
    time_str: str,
) -> bool:
    heading, body_html = _appointment_confirmation_html(
        patient_name, doctor_name, date_str, time_str
    )
    subject = f"ClinIQ — Appointment Confirmed with Dr. {doctor_name}"
    html = _build_html_email(
        subject, heading, body_html, cta_text="View Appointment", cta_url="#"
    )
    return _send(to_email, subject, html)


def send_welcome_email(to_email: str, patient_name: str) -> bool:
    heading, body_html = _welcome_html(patient_name)
    subject = "Welcome to ClinIQ — The intelligence your clinic never had."
    html = _build_html_email(
        subject,
        heading,
        body_html,
        cta_text="Go to Dashboard",
        cta_url="https://patient-project-seven.vercel.app/",
    )
    return _send(to_email, subject, html)


def send_email_notification(to_email: str, subject: str, body: str) -> bool:
    """Generic fallback — sends a plain body wrapped in the ClinIQ template."""
    body_html = f'<p style="color:#6B635A;line-height:1.7;">{body.replace(chr(10), "<br/>")}</p>'
    html = _build_html_email(subject, subject, body_html)
    return _send(to_email, subject, html)
