import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management import BaseCommand
from django.template.loader import render_to_string

from notifications.email.sender import send_club_email
from notifications.telegram.common import send_telegram_message, Chat
from users.models.user import User

log = logging.getLogger(__name__)

TIMEDELTA = timedelta(days=14)


class Command(BaseCommand):
    help = "Send subscription expired emails"

    def add_arguments(self, parser):
        parser.add_argument("--production", type=bool, required=False, default=False)

    def handle(self, *args, **options):
        # select daily subscribers
        if not options.get("production"):
            about_to_expire_users = User.objects.filter(
                email__in=dict(settings.ADMINS).values(),
                telegram_id__isnull=False
            )
        else:
            about_to_expire_users = User.objects\
                .filter(
                    membership_expires_at__gte=datetime.utcnow() + TIMEDELTA,
                    membership_expires_at__lt=datetime.utcnow() + TIMEDELTA + timedelta(days=1),
                    moderation_status=User.MODERATION_STATUS_APPROVED,
                    deleted_at__isnull=True,
                )\
                .exclude(is_email_unsubscribed=True)\
                .exclude(membership_platform_type=User.MEMBERSHIP_PLATFORM_PATREON)

        for user in about_to_expire_users:
            if user.membership_platform_data and user.membership_platform_data.get("recurrent"):
                self.stdout.write(f"User {user.email} has recurrent subscription, skipping...")
                continue

            if not user.is_email_unsubscribed:
                self.stdout.write(f"Sending email to {user.email}...")

                try:
                    email = render_to_string("emails/subscription_expired.html", {
                        "user": user,
                    })

                    send_club_email(
                        recipient=user.email,
                        subject=f"Ваша клубная карта скоро истечёт 😱",
                        html=email,
                        tags=["subscription_expire"]
                    )
                except Exception as ex:
                    self.stdout.write(f"Email to {user.email} failed: {ex}")
                    log.exception(f"Email to {user.email} failed: {ex}")

            if user.telegram_id:
                self.stdout.write(f"Sending telegram message to {user.email}...")

                message = render_to_string("messages/subscription_expired.html", {
                    "user": user,
                })

                try:
                    send_telegram_message(
                        chat=Chat(id=user.telegram_id),
                        text=message,
                    )
                except Exception as ex:
                    self.stdout.write(f"Telegram to {user.email} failed: {ex}")

        self.stdout.write("Done 🥙")
