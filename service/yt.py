from yt_dlp import YoutubeDL
import shutil
import os
import re

class Yt:
    def __init__(self, redis):
        self.r = redis
        pass
    def download(self, playlist, type, url, id, session):
        pipe = self.r.pipeline()
        pipe.expire(id, int(os.getenv('DATA_REDIS_EXP_SECONDS')))

        pipe.hset(id, mapping={'status': 'Vídeo em processamento.', 'session': session})
        pipe.publish(id, 'updated')
        pipe.execute()

        def progress_hook(d):
            if d['status'] == 'downloading':
                info = d['info_dict']
                title = info.get('title')
                fmt = info.get('format', '')

                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                speed = d.get('speed')
                eta = d.get('eta')

                if total:
                    pct = downloaded / total * 100
                    total_mb = total / (1024*1024)
                    downloaded_mb = downloaded / (1024*1024)
                    pct_str = f"{pct:.1f}% of {total_mb:.2f}MiB"
                else:
                    pct_str = f"{downloaded / (1024*1024):.2f}MiB"

                speed_str = f"at {speed / (1024*1024):.2f}MiB/s" if speed else ""
                eta_str = f"ETA {int(eta//3600):02}:{int((eta%3600)//60):02}:{int(eta%60):02}" if eta else ""

                status_msg = f"[download] {pct_str} {speed_str} {eta_str}"

                pipe.hset(id, mapping={'status': f"{title}[{fmt}] {status_msg}", 'session': session})
                pipe.publish(id, 'updated')
                pipe.execute()

                if downloaded > int(os.getenv('MAX_DOWNLOAD_BYTES')):
                    raise Exception('Tamanho máximo permitido para download atingido.')
            elif d['status'] == 'finished':
                info = d['info_dict']
                title = d['info_dict'].get('title')
                fmt = info.get('format', '')
                pipe.hset(id, mapping={'status': f'{title}[{fmt}] foi processado com sucesso.', 'session': session})
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
            'progress_hooks': [progress_hook],
            'quiet': True,
            'progress_with_newline': True,
            'no_color': True
        }

        ydl_opts_video = {
            'yes_playlist': playlist,
            'outtmpl': outputPath,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'recode_video': 'mp4',
            'progress_hooks': [progress_hook],
            'quiet': True,
            'progress_with_newline': True,
            'no_color': True
        }

        if playlist == False:
            opts = ydl_opts_video if type == 1 else ydl_opts_audio

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url)
                filename = ydl._prepare_filename(info)
                pipe.hset(id, mapping={'status': 'O download do arquivo será iniciado em instantes.', 'session': session})   
                pipe.publish(id, 'updated')
                pipe.execute()
                return True
        else:
            opts = ydl_opts_video if type == 1 else ydl_opts_audio

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url)
                filename = ydl._prepare_filename(info)
                print("print " + filename)
                originPath = filename.replace('NA/', '').replace('.NA', '')
                self.sanitizeFolderFiles(originPath)
                print("print " + originPath)
                shutil.make_archive(originPath, 'zip', originPath)
                shutil.rmtree(originPath)
                pipe.hset(id, mapping={'status': 'O download do arquivo será iniciado em instantes.', 'session': session})
                pipe.publish(id, 'updated')
                pipe.execute()
                return True

        pipe.hset(id, mapping={'status': 'O download do vídeo não pôde ser realizado.', 'session': session})
        pipe.publish(id, 'updated')
        pipe.execute()
        return False

    def sanitizeFolderFiles(self, folder_path):
        for root, dirs, files in os.walk(folder_path):
            for name in files:
                safeName = re.sub(r'[^\w\s\-.]', '_', name, flags=re.UNICODE)
                if name != safeName:
                    os.rename(os.path.join(root, name), os.path.join(root, safeName))