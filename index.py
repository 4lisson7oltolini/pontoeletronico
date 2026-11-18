import os
import resend
from resend.exceptions import ResendError

resend.api_key = os.environ["RESEND_API_KEY"]

params: resend.Emails.SendParams = {
    "from": "Acme <onboarding@resend.dev>",
    "to": ["alissonvoltolinidev@gmail.com"],
    "subject": "hello world",
    "html": "<strong>it works!</strong>",
}

try:
    email = resend.Emails.send(params)
    print(email)
except ResendError as error:
    print(error)