"""Neon terminal palette and responsive layout."""

CSS = """
Screen {
    background: #080c16;
    color: #d4def1;
}
#top {
    height: 3;
    padding: 0 2;
    background: #0d1425;
    border-bottom: solid #273754;
}
#main {
    height: 1fr;
}
#sidebar {
    width: 23;
    padding: 1;
    background: #0b1020;
    border-right: solid #23324b;
}
#nav-brand {
    color: #b6a0ff;
    height: 3;
    text-style: bold;
}
#sidebar .head {
    color: #7184a5;
    height: 2;
    margin-top: 1;
}
#session-scroll {
    height: 1fr;
}
#sessions {
    height: auto;
}
#sessions Button {
    width: 100%;
    height: 3;
    min-width: 0;
    border: none;
    background: transparent;
    color: #9aaac7;
    text-align: left;
    padding: 1;
}
#sessions Button:hover {
    background: #16213a;
    color: #d4def1;
}
#sessions Button.current {
    background: #162e3c;
    color: #69f4df;
    text-style: bold;
    border-left: tall #69f4df;
}
#new {
    width: 100%;
    min-width: 0;
    height: 3;
    background: #1b233c;
    color: #d4c6ff;
    border: round #554476;
}
#new:hover {
    border: round #b6a0ff;
    background: #2b2344;
}
#nav-note {
    height: 3;
    color: #586b8c;
}
#conversation {
    width: 1fr;
}
#chat-heading {
    height: 3;
    padding: 1 2 0 2;
    border-bottom: solid #18243b;
}
#chat-title {
    width: 1fr;
    color: #9db2d3;
    text-style: bold;
}
#channel-tag {
    width: 9;
    color: #608293;
    text-align: right;
}
#turn-report {
    height: 2;
    padding: 0 2;
    color: #7189a8;
    background: #0b1220;
}
#chat {
    height: 1fr;
    padding: 0 3 1 3;
    scrollbar-color: #315269;
    scrollbar-background: #0b1020;
    scrollbar-size-vertical: 1;
}
#welcome {
    height: auto;
    margin-top: 2;
    padding: 2 1;
    color: #92a5c5;
    text-align: center;
}
.msg-user {
    background: #141a2e;
    border-left: tall #ff79c8;
    color: #eee4f4;
    padding: 1 2;
    margin-top: 1;
}
.msg-tag {
    color: #69f4df;
    margin-top: 1;
    padding: 0 1;
    text-style: bold;
}
.msg-state {
    color: #ffd58a;
    background: #211c24;
    border-left: tall #a47b55;
    padding: 0 1;
    margin-top: 1;
}
.turn-summary {
    color: #83bcbb;
    border-left: tall #31585d;
    background: #0d1b25;
    padding: 0 1;
    margin: 1 0;
}
Markdown {
    margin: 0 0 1 0;
    padding: 0 1;
    background: transparent;
    color: #c7d5ed;
}
Collapsible {
    margin: 1 0 0 1;
    padding: 0;
    border: round #283c50;
    background: #0e1927;
}
CollapsibleTitle {
    color: #8fc5d2;
    background: transparent;
}
Collapsible Static {
    color: #9db2cc;
}
#right-rail {
    width: 35;
    border-left: solid #23324b;
    background: #0b1020;
    padding: 1;
}
#companion {
    height: 1fr;
    border: round #2d405b;
    background: #0b1020;
}
#companion-title {
    height: 2;
    padding: 0 1;
    color: #7085a9;
}
#companion-name {
    height: 2;
    color: #d4c6ff;
    text-align: center;
    text-style: bold;
}
#pet {
    height: 1fr;
    min-height: 10;
    content-align: center middle;
    background: #0b1020;
}
#pet-hint {
    height: 2;
    color: #526784;
    text-align: center;
}
#activity-status {
    height: 2;
    padding: 0 1;
    color: #7292a6;
    text-align: center;
}
#panel {
    height: 1fr;
    min-height: 8;
    display: none;
    padding: 0 1;
    border-top: solid #3e3155;
    scrollbar-size-vertical: 1;
}
#panel.open {
    display: block;
}
#right-rail.controls-open #companion {
    height: 17;
    min-height: 12;
    border-bottom: none;
}
#right-rail.controls-open #pet {
    min-height: 6;
}
#panel .head {
    color: #ff79c8;
    margin-top: 1;
    text-style: bold;
}
#panel Checkbox {
    width: 100%;
    height: 1;
    padding: 0;
    border: none;
    background: transparent;
    color: #a5bbd7;
}
#audio-buttons {
    height: 3;
    margin-top: 1;
}
#audio-buttons Button {
    width: 1fr;
    padding: 0;
    margin-right: 1;
    color: #9bd9d2;
}
#activity-report {
    height: auto;
    color: #8ba5bf;
    padding: 1 0;
}
#activity-timeline {
    height: 12;
    min-height: 5;
    border-left: solid #273e55;
    padding-left: 1;
    scrollbar-color: #315269;
    scrollbar-size-vertical: 1;
}
#activity-lines {
    height: auto;
    color: #879db8;
}
#clear-activity {
    width: 100%;
    color: #b6a0cc;
    margin-top: 1;
}
#mem-query {
    height: 3;
    background: #0b1020;
    border: round #31435b;
}
#memories, #approvals {
    height: auto;
}
.item {
    color: #a9b8d2;
    margin: 0 0 1 0;
}
#panel Button {
    min-width: 8;
    height: 3;
    background: #1c283d;
    border: none;
}
#bar {
    height: 8;
    padding: 0 2;
    background: #0b1120;
    border-top: solid #25334b;
}
#compose-label {
    height: 1;
    color: #7288ab;
}
#compose-line {
    height: 3;
}
#prompt {
    width: 1fr;
    height: 3;
    border: round #34445f;
    background: #10182b;
    color: #e0e9fc;
}
#prompt:focus {
    border: round #69f4df;
    background: #111e30;
}
#send {
    width: 14;
    min-width: 0;
    height: 3;
    padding: 0;
    margin-left: 1;
    border: round #69f4df;
    background: #69f4df;
    color: #09232b;
    text-style: bold;
}
#send:hover {
    background: #ff79c8;
    border: round #ff79c8;
    color: #22152c;
}
#ptt {
    width: 8;
    min-width: 0;
    height: 3;
    padding: 0;
    margin-left: 1;
    color: #a8e6df;
    border: round #315b68;
    background: #122632;
}
#ptt.recording {
    color: #180e17;
    background: #ff8193;
    border: round #ff8193;
}
#voice-status {
    height: 1;
    color: #5e8299;
}
#voice-status.recording {
    color: #ff8193;
    text-style: bold;
}
#compose-options {
    height: 2;
}
#bar Checkbox {
    width: auto;
    height: 1;
    margin-right: 1;
    padding: 0;
    border: none;
    background: transparent;
    color: #8296b7;
}
#bar Checkbox:focus {
    color: #b6a0ff;
}
Footer {
    height: 1;
    background: #121a2d;
    color: #7288ab;
}
Screen.compact-nav #sidebar {
    display: none;
}
Screen.compact-nav.nav-open #sidebar {
    display: block;
}
Screen.narrow #right-rail {
    width: 26;
    padding: 0;
}
Screen.narrow #chat {
    padding: 0 1;
}
Screen.narrow #bar {
    padding: 0 1;
}
Screen.narrow #send {
    width: 6;
}
Screen.narrow #ptt {
    width: 5;
}
Screen.narrow #chat-heading {
    padding: 1 1 0 1;
}
Screen.short #companion-title {
    height: 1;
}
Screen.short #turn-report {
    height: 1;
}
Screen.short #companion-name {
    height: 1;
}
Screen.short #pet-hint {
    height: 1;
}
Screen.short #pet {
    min-height: 7;
}
Screen.nav-hidden #sidebar {
    display: none;
}
Screen.short #right-rail.controls-open #companion {
    height: 10;
    min-height: 8;
}
Screen.short #right-rail.controls-open #companion-title,
Screen.short #right-rail.controls-open #companion-name,
Screen.short #right-rail.controls-open #pet-hint {
    display: none;
}
Screen.short #right-rail.controls-open #pet {
    min-height: 5;
}
"""
