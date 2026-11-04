"""Small presentation widgets; all chat and control actions remain in B12App."""

from datetime import datetime

from rich.cells import cell_len
from rich.text import Text
from textual.widgets import Static


class NeonHeader(Static):
    connected = False
    preview = False

    def on_mount(self):
        self.set_interval(1, self.refresh)

    def set_connected(self, connected: bool):
        self.connected = connected
        self.refresh()

    def render(self):
        width = max(40, self.content_size.width)
        label = "  B ▪ 12  "
        title = "  NEON COMPANION"
        clock = datetime.now().strftime("%H:%M")
        text = Text(no_wrap=True, overflow="crop")
        text.append(label, "bold #09232b on #69f4df")
        text.append(title, "bold #dce7ff")
        text.append(" " * max(1, width - len(label + title + clock)), "#0d1425")
        text.append(clock, "#8f9fc1")
        subtitle = (
            "  ВІЗУАЛЬНИЙ ПЕРЕГЛЯД · БЕЗ СЕРВЕРА"
            if self.preview
            else "  твій простір для розмов і задумів"
        )
        text.append("\n" + subtitle, "#7186ab")
        status = "◇ ДЕМО" if self.preview else "● LOCAL LINK" if self.connected else "○ OFFLINE"
        text.append(" " * max(1, width - cell_len(subtitle) - cell_len(status)))
        text.append(status, "#69f4df" if self.connected else "#ffd58a")
        return text


class Welcome(Static):
    def render(self):
        text = Text(justify="center")
        text.append("╭───  B ▪ 12  ───╮\n", "bold #69f4df")
        text.append("Тут починається\nнаша наступна історія.\n\n", "bold #dce7ff")
        text.append("Запитай. Досліди. Придумай.\n", "#8d9fc0")
        text.append("Кіберкіт уже поруч.", "#b6a0ff")
        return text
