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
# Chave usada para assinar e validar JWTs
KEY_JWT=chave_super_secreta_jwt

# Senha usada para autenticação
CORRECT_PASSWORD=senha_forte_aqui

# Tempo de expiração do JWT em minutos
JWT_EXP_MINUTES=60

# Tempo de expiração para links de arquivos (em minutos)
FILES_EXP_MINUTES=120

# Tempo de expiração dos dados no Redis (em segundos)
DATA_REDIS_EXP_SECONDS=3600

# Limite máximo de download em bytes (ex: 50MB = 52428800)
MAX_DOWNLOAD_BYTES=52428800

# Limite de requisições simultâneas com semáforo
SEMAPHORE_LIMIT=10

# Chave secreta para a aplicação
SECRET_KEY=chave_super_secreta_app

# Configuração de conexão com o Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Portas da aplicação
WEB_PORT_EXTERNAL=8080   # Porta exposta para o usuário final
WEB_PORT_INTERNAL=8000   # Porta interna usada pelo container/servidor

# Número de workers do Gunicorn (processos para lidar com requisições)
GUNICORN_WORKERS=4
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
