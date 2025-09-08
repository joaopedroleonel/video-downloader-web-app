# Video Downloader Web App

Uma aplicação web para download de vídeos e áudios de URLs (incluindo playlists), com suporte a filas de tarefas via Redis, atualização de status em tempo real via WebSocket e download de arquivos processados.

## Funcionalidades

- Download de vídeos ou áudios via `yt-dlp`
- Suporte a playlists
- Atualização de status em tempo real usando **Flask-SocketIO**
- Compactação automática em ZIP para playlists
- Armazenamento temporário de arquivos em `/app/files`
- Limpeza automática de pastas antigas (mais de 30 minutos)
- Autenticação via token JWT
- Fila de downloads com Redis

## Tecnologias

- Python 3.12
- Flask
- Flask-SocketIO
- Eventlet
- Redis
- yt-dlp
- Gunicorn
- Docker & Docker Compose

## Configuração

### 1. Variáveis de ambiente

Crie um arquivo `.env` com:

```dotenv
WEB_PORT=5000
REDIS_PORT=6379
SECRET_KEY=uma_chave_secreta
KEY_JWT=uma_chave_jwt
CORRECT_PASSWORD=sua_senha
REDIS_HOST=redis
REDIS_PORT=6379
````

### 2. Build & Run com Docker

```bash
docker-compose build
docker-compose up
```

A aplicação ficará disponível em `http://localhost:5000` (ou na porta definida em `WEB_PORT`).

## Estrutura de diretórios

```
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── main.py
├── readme.md
├── .env
├── service/
│   ├── __init__.py
│   ├── auth.py
│   ├── clean.py
│   └── yt.py
├── web/
│   ├── static/
│   │   ├── css/
│   │   │   └── styles.css
│   │   ├── images/
│   │   │   └── icon.svg
│   │   └── js/
│   │       └── socket.io.js
│   ├── auth.html
│   └── index.html
└── files/   # pasta criada dinamicamente para armazenar downloads

```

## Endpoints

### `/auth`

* `GET`: Retorna a página de login
* `POST`: Recebe JSON `{ "password": "senha" }` e retorna um token em cookie HTTPOnly se correto

### `/initDownload`

* `POST`: Recebe JSON `{ "url": "...", "type": 1|2, "playlist": true|false }`
* Retorna `{ "uuid": "id_do_job" }`
* O download é processado em background usando Redis como fila

### `/download/<jobId>`

* Retorna o arquivo baixado para download

### WebSocket `/checkStatus`

* Recebe `{ "jobId": "..." }`
* Retorna atualizações de status em tempo real

## Observações importantes

* Os arquivos baixados ficam em `/app/files/<uuid>/...`. Playlists são compactadas em ZIP.
* A limpeza automática remove pastas com mais de 30 minutos a cada 1 minuto.
* `gunicorn` está configurado com Eventlet (`-k eventlet`) para suportar WebSocket.
