"""
Модуль для генерации графиков.
"""

import io
import logging
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)
plt.style.use("ggplot")


async def generate_user_growth_chart(growth_data: Dict[str, int]) -> io.BytesIO:
    """Генерирует график роста пользователей."""
    try:
        dates = []
        counts = []

        for date_str, count in sorted(growth_data.items()):
            dates.append(datetime.strptime(date_str, "%Y-%m-%d"))
            counts.append(count)

        plt.figure(figsize=(10, 6))
        plt.plot(dates, counts, marker="o", linestyle="-", color="#2c7be5", linewidth=2, markersize=8)
        plt.fill_between(dates, counts, color="#2c7be5", alpha=0.3)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        plt.gcf().autofmt_xdate()
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.title("Динамика новых пользователей за неделю", fontsize=16, pad=20)
        plt.xlabel("Дата", fontsize=12, labelpad=10)
        plt.ylabel("Количество новых пользователей", fontsize=12, labelpad=10)

        for i, count in enumerate(counts):
            plt.annotate(str(count), (dates[i], counts[i]), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=10, weight="bold")

        plt.ylim(bottom=0)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=100)
        buf.seek(0)
        plt.close()

        return buf
    except Exception as e:
        logger.exception(f"Error generating user growth chart: {e}")
        raise


async def generate_message_count_chart(messages_data: Dict[str, int]) -> io.BytesIO:
    """Генерирует график количества сообщений."""
    try:
        dates = []
        counts = []

        for date_str, count in sorted(messages_data.items()):
            dates.append(datetime.strptime(date_str, "%Y-%m-%d"))
            counts.append(count)

        plt.figure(figsize=(10, 6))
        plt.plot(dates, counts, marker="o", linestyle="-", color="#e55c2c", linewidth=2, markersize=8)
        plt.fill_between(dates, counts, color="#e55c2c", alpha=0.3)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        plt.gcf().autofmt_xdate()
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.title("Количество отправленных сообщений за неделю", fontsize=16, pad=20)
        plt.xlabel("Дата", fontsize=12, labelpad=10)
        plt.ylabel("Количество сообщений", fontsize=12, labelpad=10)

        for i, count in enumerate(counts):
            plt.annotate(str(count), (dates[i], counts[i]), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=10, weight="bold")

        plt.ylim(bottom=0)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=100)
        buf.seek(0)
        plt.close()

        return buf
    except Exception as e:
        logger.exception(f"Error generating message count chart: {e}")
        raise