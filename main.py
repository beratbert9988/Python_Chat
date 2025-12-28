import flet as ft
import socket
import threading
import json
import time

# --- Socket Logic ---

class SocketManager:
    def __init__(self):
        self.socket = None
        self.running = False
        self.on_message_received = None
        self.on_status_change = None

    def log(self, message):
        if self.on_status_change:
            self.on_status_change(message)

class ServerNode(SocketManager):
    def __init__(self, host="0.0.0.0", port=5000):
        super().__init__()
        self.host = host
        self.port = port
        self.clients = []

    def start(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.running = True
            self.log(f"Server started on {self.host}:{self.port}")
            
            thread = threading.Thread(target=self.accept_clients, daemon=True)
            thread.start()
        except Exception as e:
            self.log(f"Server error: {e}")

    def accept_clients(self):
        while self.running:
            try:
                client_conn, addr = self.socket.accept()
                self.log(f"New connection from {addr}")
                self.clients.append(client_conn)
                threading.Thread(target=self.handle_client, args=(client_conn, addr), daemon=True).start()
            except:
                break

    def handle_client(self, conn, addr):
        while self.running:
            try:
                data = conn.recv(1024).decode('utf-8')
                if not data:
                    break
                self.log(f"Received from {addr}: {data}")
                self.broadcast(data, exclude=conn)
                if self.on_message_received:
                    self.on_message_received(data)
            except:
                break
        conn.close()
        if conn in self.clients:
            self.clients.remove(conn)
        self.log(f"Connection closed: {addr}")

    def broadcast(self, message, exclude=None):
        for client in self.clients:
            if client != exclude:
                try:
                    client.send(message.encode('utf-8'))
                except:
                    client.close()
                    if client in self.clients:
                        self.clients.remove(client)

    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()
        for c in self.clients:
            c.close()

class ClientNode(SocketManager):
    def __init__(self, host="127.0.0.1", port=5000):
        super().__init__()
        self.host = host
        self.port = port

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.running = True
            self.log(f"Connected to server at {self.host}:{self.port}")
            
            threading.Thread(target=self.receive_messages, daemon=True).start()
            return True
        except Exception as e:
            self.log(f"Connection failed: {e}")
            return False

    def receive_messages(self):
        while self.running:
            try:
                data = self.socket.recv(1024).decode('utf-8')
                if not data:
                    break
                if self.on_message_received:
                    self.on_message_received(data)
            except:
                break
        self.log("Disconnected from server.")
        self.running = False

    def send(self, message):
        if self.socket and self.running:
            try:
                self.socket.send(message.encode('utf-8'))
            except Exception as e:
                self.log(f"Send error: {e}")

    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()

# --- Flet UI ---

def main(page: ft.Page):
    page.title = "Flet P2P Messenger"
    page.theme_mode = "dark"
    page.window_width = 450
    page.window_height = 700
    page.vertical_alignment = "start"

    node = None
    username = "User"

    # --- UI Components ---
    
    chat_list = ft.ListView(expand=True, spacing=10, padding=20, auto_scroll=True)
    msg_input = ft.TextField(hint_text="Type a message...", expand=True, on_submit=lambda e: send_click(None))
    status_text = ft.Text("Ready", color="grey400", size=12)

    def update_status(text):
        status_text.value = f"Status: {text}"
        page.update()

    def add_message(msg_json, is_me=False):
        try:
            data = json.loads(msg_json)
            sender = data.get("user", "Unknown")
            text = data.get("text", "")
            timestamp = data.get("time", "")
        except:
            sender = "System"
            text = msg_json
            timestamp = time.strftime("%H:%M")

        alignment = "end" if is_me else "start"
        color = "blue700" if is_me else "grey800"

        chat_list.controls.append(
            ft.Column(
                [
                    ft.Text(f"{sender} • {timestamp}", size=10, color="grey500"),
                    ft.Container(
                        content=ft.Text(text, color="white"),
                        bgcolor=color,
                        padding=12,
                        border_radius=ft.BorderRadius.all(15),
                    ),
                ],
                horizontal_alignment=alignment,
            )
        )
        page.update()

    def on_msg(data):
        add_message(data, is_me=False)

    def send_click(e):
        if not msg_input.value or not node or not node.running:
            return
        
        msg_data = {
            "user": username,
            "text": msg_input.value,
            "time": time.strftime("%H:%M")
        }
        msg_json = json.dumps(msg_data)
        
        if isinstance(node, ClientNode):
            node.send(msg_json)
        elif isinstance(node, ServerNode):
            node.broadcast(msg_json)
            
        add_message(msg_json, is_me=True)
        msg_input.value = ""
        page.update()

    # --- View Transitions ---

    def show_setup_view():
        page.clean()
        
        name_field = ft.TextField(label="Your Name", value="User")
        host_field = ft.TextField(label="Host/IP", value="127.0.0.1")
        port_field = ft.TextField(label="Port", value="5000")

        def start_server(e):
            nonlocal node, username
            username = name_field.value
            node = ServerNode(port=int(port_field.value))
            node.on_status_change = update_status
            node.on_message_received = on_msg
            node.start()
            show_chat_view("Server Mode")

        def start_client(e):
            nonlocal node, username
            username = name_field.value
            node = ClientNode(host=host_field.value, port=int(port_field.value))
            node.on_status_change = update_status
            node.on_message_received = on_msg
            if node.connect():
                show_chat_view(f"Connected to {host_field.value}")

        page.add(
            ft.Column([
                ft.Text("Messenger Setup", size=30, weight="bold"),
                name_field,
                ft.Divider(),
                ft.Text("Connection Settings", size=16),
                host_field,
                port_field,
                ft.Row([
                    ft.FilledButton("Start as Server", icon="dns", on_click=start_server, expand=True),
                    ft.FilledButton("Join as Client", icon="login", on_click=start_client, expand=True),
                ]),
            ], spacing=20, alignment="center")
        )

    def show_chat_view(title):
        page.clean()
        page.title = f"Messenger - {title}"
        
        page.add(
            ft.AppBar(
                title=ft.Text(f"Chat: {username} ({title})"),
                bgcolor="surfacevariant",
            ),
            chat_list,
            status_text,
            ft.Container(
                content=ft.Row([
                    msg_input,
                    ft.IconButton("send", on_click=send_click)
                ]),
                padding=10
            )
        )
        page.update()

    show_setup_view()

if __name__ == "__main__":
    # Note: For Cloudflare Tunnel, run: cloudflared tunnel --url tcp://localhost:5000
    # Then clients connect to the generated .trycloudflare.com address (or your domain)
    ft.run(main)
