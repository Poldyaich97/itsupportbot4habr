import smtplib
from email.mime.text import MIMEText
from my_secrets import smtp_server, smtp_port, smtp_user, smtp_password, support_email


def send_request_email(subject: str, body: str):
    msg = MIMEText(body)
    msg["From"] = smtp_user
    msg["To"] = support_email
    msg["Subject"] = subject

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            if server.has_extn("STARTTLS"):
                server.starttls()
                server.ehlo()
            if server.has_extn("AUTH"):
                server.login(smtp_user, smtp_password)

            server.sendmail(smtp_user, support_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Ошибка при отправке письма: {e}")
        return False
