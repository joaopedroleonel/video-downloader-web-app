function resetIu() {
    document.getElementById('download-btn').removeAttribute('disabled');
    document.getElementById('url').value = '';
    document.getElementById('playlist').checked = false;
}

document.getElementById('url').addEventListener('input', function (event) {
    if((event.target.value).toLowerCase().includes('playlist')){
        document.getElementById('playlist').checked = true;
    } else {
        document.getElementById('playlist').checked = false;
    }
});

document.getElementById('form').addEventListener('submit', async function (event) {
    event.preventDefault();
    document.getElementById('status').textContent = '';

    const url = document.getElementById('url').value;
    const isPlaylist = document.getElementById('playlist').checked;
    const format = document.querySelector('input[name="format"]:checked').value;

    const payload = {
        'playlist': isPlaylist,
        'type': Number(format),
        'url': url
    }

    if (url) {
        try {
            const downloadBtn = document.getElementById('download-btn');
            downloadBtn.setAttribute('disabled', '');
            const statusElement = document.getElementById('status');
            statusElement.textContent = 'Conectando ao servidor.';

            const response = await fetch("/initDownload", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const data = await response.json();
                if (data && data.uuid) {
                    const socket = io();
                    const jobId = data.uuid;

                    socket.emit('checkStatus', { jobId });

                    socket.on('statusUpdate', (checkData) => {
                        if (checkData.status) {
                            statusElement.textContent = checkData.msg;

                            if (checkData.status === 'finally') {
                                const link = document.createElement('a');
                                link.href = `/download/${jobId}`;
                                link.download = '';
                                link.click();
                                resetIu();
                                socket.disconnect();
                            }

                            if (checkData.status === 'error') {
                                document.getElementById('download-btn').removeAttribute('disabled');
                                socket.disconnect();
                            }
                        } else if (checkData.error) {
                            statusElement.textContent = 'Não foi possível realizar o download do vídeo.';
                            document.getElementById('download-btn').removeAttribute('disabled');
                            socket.disconnect();
                        }
                    });
                }
            } else if(response.status == '401'){
                window.location.reload();
            } else {
                statusElement.textContent = 'Não foi possível realizar o download do vídeo.';
                document.getElementById('download-btn').removeAttribute('disabled');
            }
        } catch (error) {
            statusElement.textContent = 'Não foi possível realizar o download do vídeo.';
            document.getElementById('download-btn').removeAttribute('disabled');
        }
    }
});