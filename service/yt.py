from yt_dlp import YoutubeDL
import shutil
import os
import re
import shutil
from pathlib import Path

class Yt:
    def __init__(self, redis):
        self.r = redis
        pass
    def download(self, playlist, type, url, id, session):
        pipe = self.r.pipeline()
        pipe.expire(id, int(os.getenv('DATA_REDIS_EXP_SECONDS')))

        pipe.hset(id, mapping={'status': 'running', 'msg': 'Vídeo em processamento.', 'session': session})
        pipe.publish(id, 'updated')
        pipe.execute()

        def progressHook(d):
            if d['status'] == 'downloading':
                info = d['info_dict']
                title = info.get('title')
                fmt = info.get('format', '')

                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate')

                if total:
                    pct = downloaded / total * 100
                    totalMb = total / (1024*1024)
                    pctStr = f'{pct:.1f}% of {totalMb:.2f}MiB'
                else:
                    pctStr = f'{downloaded / (1024*1024):.2f}MiB'

                pipe.hset(id, mapping={'status': 'running', 'msg': f'{title}[{fmt}] {pctStr}.', 'session': session})
                pipe.publish(id, 'updated')
                pipe.execute()

                if sum(f.stat().st_size for f in Path('/app/files').rglob('*') if f.is_file()) > int(os.getenv('MAX_DOWNLOAD_BYTES')):
                    raise Exception('O tamanho máximo da pasta de downloads foi atingido.')
            elif d['status'] == 'finished':
                info = d['info_dict']
                title = d['info_dict'].get('title')
                fmt = info.get('format', '')

                pipe.hset(id, mapping={'status': 'running', 'msg': f'{title}[{fmt}] foi processado com sucesso.', 'session': session})
                pipe.publish(id, 'updated')
                pipe.execute()

        outputPath = f'./files/{id}/%(playlist_title)s/%(title)s.%(ext)s' if playlist else f'./files/{id}/%(title)s.%(ext)s'

        ydl_opts_audio = {
            'yes_playlist': playlist,
            'outtmpl': outputPath,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '0', 
            }],
            'progress_hooks': [progressHook],
            'quiet': True,
            'progress_with_newline': True,
            'no_color': True
        }

        ydl_opts_video = {
            'yes_playlist': playlist,
            'outtmpl': outputPath,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }],
            'progress_hooks': [progressHook],
            'quiet': True,
            'progress_with_newline': True,
            'no_color': True
        }
        
        opts = ydl_opts_video if type == 1 else ydl_opts_audio

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url)
            filename = ydl._prepare_filename(info)

            if playlist:
                originPath = filename.replace('NA/', '').replace('.NA', '')
                self.sanitizeFolderFiles(originPath)
                shutil.make_archive(originPath, 'zip', originPath)
                shutil.rmtree(originPath)
            
            pipe.hset(id, mapping={'status': 'finally', 'msg': 'O download do arquivo será iniciado em instantes.', 'session': session})
            pipe.publish(id, 'updated')
            pipe.execute()
            return

        pipe.hset(id, mapping={'status': 'error', 'status': 'O download do vídeo não pôde ser realizado.', 'session': session})
        pipe.publish(id, 'updated')
        pipe.execute()
        return

    def sanitizeFolderFiles(self, folder_path):
        for root, dirs, files in os.walk(folder_path):
            for name in files:
                safeName = re.sub(r'[^\w\s\-.]', '_', name, flags=re.UNICODE)
                if name != safeName:
                    os.rename(os.path.join(root, name), os.path.join(root, safeName))