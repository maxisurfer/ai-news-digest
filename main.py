#!/usr/bin/env python3
"""
AI News Bot - Main Application

Generates and distributes daily AI news digests using configurable LLM providers.
"""
import argparse
import sys
from datetime import datetime
from src.config import Config
from src.logger import setup_logger
from src.news import NewsGenerator
from src.news.history import append_sent_items
from src.notifiers import (
    EmailNotifier,
    WebhookNotifier,
    SlackNotifier,
    TelegramNotifier,
    DiscordNotifier
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate and send the news digest")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and generate the digest, print it to the log, do not send notifications",
    )
    return parser.parse_args()


def main():
    """Main application entry point"""
    try:
        args = parse_args()

        # Load configuration
        config = Config()
        dry_run = config.dry_run or args.dry_run

        # Setup logger with config
        logger = setup_logger(
            "ai_news_bot",
            level=config.log_level,
            log_format=config.log_format
        )

        # English-only digest (topic sources are English)
        languages = ["en"]
        
        logger.info("=" * 60)
        logger.info("AI News Bot Starting")
        logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"LLM Provider: {config.llm_provider}")
        if config.llm_model:
            logger.info(f"LLM Model: {config.llm_model}")
        logger.info(f"Languages: {', '.join(languages)}")
        logger.info(f"Web Search: {config.enable_web_search}")
        if dry_run:
            logger.info("DRY RUN: notifications disabled, full digest will be printed")
        logger.info("=" * 60)

        # Initialize news generator once
        logger.info("Initializing news generator...")
        news_gen = NewsGenerator(
            provider_name=config.llm_provider,
            api_key=config.llm_api_key,
            model=config.llm_model,
            enable_web_search=config.enable_web_search
        )

        # Get enabled notification methods
        notification_methods = [] if dry_run else config.notification_methods
        if dry_run:
            logger.info("Enabled notification methods: (none — dry run)")
        else:
            logger.info(f"Enabled notification methods: {notification_methods}")
            known = {"email", "webhook", "slack", "telegram", "discord"}
            for method in notification_methods:
                if method not in known:
                    logger.warning(
                        f"Unknown notification method '{method}' in NOTIFICATION_METHODS — "
                        "it will not match any sender (use email, discord, or email,discord)"
                    )

        # Track overall results
        overall_results = {"sent": [], "failed": []}
        
        # Process each language
        for language in languages:
            logger.info("=" * 60)
            logger.info(f"Processing language: {language.upper()}")
            logger.info("=" * 60)

            try:
                # Generate news digest for this language
                logger.info(f"Generating AI news digest in {language.upper()} from real-time sources...")
                digest = news_gen.generate_news_digest_from_sources(
                    language=language,
                    max_items_per_source=config.max_items_per_source,
                    stage1_template=config.stage1_prompt_template,
                    stage2_template=config.stage2_prompt_template
                )
                full_digest = digest.full_markdown
                short_digest = digest.short_markdown

                logger.info(
                    f"News digest generated for {language.upper()} "
                    f"(full {len(full_digest)} chars, short {len(short_digest)} chars)"
                )
                logger.info("-" * 60)
                if dry_run:
                    logger.info(f"News Digest (full, {language.upper()}):")
                    logger.info("-" * 60)
                    logger.info(full_digest)
                else:
                    logger.info(f"News Digest Preview ({language.upper()}):")
                    logger.info("-" * 60)
                    preview = full_digest[:500] + "..." if len(full_digest) > 500 else full_digest
                    logger.info(preview)
                logger.info("-" * 60)

                if dry_run:
                    logger.info(f"DRY RUN: skipping notifications for {language.upper()}")
                    logger.info(f"Language {language.upper()} completed successfully")
                    continue

                # Track notification results for this language
                lang_results = {"sent": [], "failed": []}

                # Send email notification if enabled
                if "email" in notification_methods:
                    try:
                        logger.info(f"Sending email notification for {language.upper()}...")
                        email_notifier = EmailNotifier()
                        if email_notifier.send(full_digest, language=language):
                            lang_results["sent"].append("email")
                            logger.info(f"Email notification sent successfully for {language.upper()}")
                        else:
                            lang_results["failed"].append("email")
                            logger.warning(f"Email notification failed for {language.upper()}")
                    except Exception as e:
                        lang_results["failed"].append("email")
                        logger.error(f"Email notification error for {language.upper()}: {e}", exc_info=True)

                # Send webhook notification if enabled
                if "webhook" in notification_methods:
                    try:
                        logger.info(f"Sending webhook notification for {language.upper()}...")
                        webhook_notifier = WebhookNotifier()
                        if webhook_notifier.send(full_digest, language=language):
                            lang_results["sent"].append("webhook")
                            logger.info(f"Webhook notification sent successfully for {language.upper()}")
                        else:
                            lang_results["failed"].append("webhook")
                            logger.warning(f"Webhook notification failed for {language.upper()}")
                    except Exception as e:
                        lang_results["failed"].append("webhook")
                        logger.error(f"Webhook notification error for {language.upper()}: {e}", exc_info=True)

                # Send Slack notification if enabled
                if "slack" in notification_methods:
                    try:
                        logger.info(f"Sending Slack notification for {language.upper()}...")
                        slack_notifier = SlackNotifier()
                        if slack_notifier.send(full_digest, language=language):
                            lang_results["sent"].append("slack")
                            logger.info(f"Slack notification sent successfully for {language.upper()}")
                        else:
                            lang_results["failed"].append("slack")
                            logger.warning(f"Slack notification failed for {language.upper()}")
                    except Exception as e:
                        lang_results["failed"].append("slack")
                        logger.error(f"Slack notification error for {language.upper()}: {e}", exc_info=True)

                # Send Telegram notification if enabled
                if "telegram" in notification_methods:
                    try:
                        logger.info(f"Sending Telegram notification for {language.upper()}...")
                        telegram_notifier = TelegramNotifier()
                        if telegram_notifier.send(full_digest, language=language):
                            lang_results["sent"].append("telegram")
                            logger.info(f"Telegram notification sent successfully for {language.upper()}")
                        else:
                            lang_results["failed"].append("telegram")
                            logger.warning(f"Telegram notification failed for {language.upper()}")
                    except Exception as e:
                        lang_results["failed"].append("telegram")
                        logger.error(f"Telegram notification error for {language.upper()}: {e}", exc_info=True)

                # Send Discord notification if enabled
                if "discord" in notification_methods:
                    try:
                        logger.info(f"Sending Discord notification for {language.upper()}...")
                        discord_notifier = DiscordNotifier()
                        if discord_notifier.send(short_digest, language=language):
                            lang_results["sent"].append("discord")
                            logger.info(f"Discord notification sent successfully for {language.upper()}")
                        else:
                            lang_results["failed"].append("discord")
                            logger.warning(f"Discord notification failed for {language.upper()}")
                    except Exception as e:
                        lang_results["failed"].append("discord")
                        logger.error(f"Discord notification error for {language.upper()}: {e}", exc_info=True)

                # Update overall results
                for method in lang_results["sent"]:
                    result_key = f"{method} ({language.upper()})"
                    if result_key not in overall_results["sent"]:
                        overall_results["sent"].append(result_key)
                
                for method in lang_results["failed"]:
                    result_key = f"{method} ({language.upper()})"
                    if result_key not in overall_results["failed"]:
                        overall_results["failed"].append(result_key)

                if lang_results["sent"] and news_gen.last_sent_items:
                    append_sent_items(news_gen.last_sent_items, config.history_days)

                logger.info(f"Language {language.upper()} completed successfully")

            except Exception as lang_error:
                logger.error(f"Error processing language {language.upper()}: {str(lang_error)}", exc_info=True)
                # Mark all notification methods as failed for this language
                for method in notification_methods:
                    result_key = f"{method} ({language.upper()})"
                    if result_key not in overall_results["failed"]:
                        overall_results["failed"].append(result_key)

        # Final Summary
        logger.info("=" * 60)
        logger.info("AI News Bot Completed")
        logger.info(f"Processed {len(languages)} language(s): {', '.join(lang.upper() for lang in languages)}")
        if dry_run:
            logger.info("DRY RUN: no notifications were sent")
        else:
            logger.info(f"Successfully sent: {', '.join(overall_results['sent']) if overall_results['sent'] else 'None'}")
            if overall_results["failed"]:
                logger.warning(f"Failed to send: {', '.join(overall_results['failed'])}")
        logger.info("=" * 60)

        # Return exit code based on results
        if not dry_run and notification_methods and not overall_results["sent"]:
            logger.error("All notifications failed")
            return 1

        return 0

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Application error: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
