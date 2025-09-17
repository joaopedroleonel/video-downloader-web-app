document.getElementById('form').addEventListener('submit', async function(event) {
    event.preventDefault();
    document.getElementById('text-error').style.display = "none";

    const payload = {
        'password': document.getElementById('password').value
    }

    const loginBtn = document.getElementById('login-btn');
    loginBtn.setAttribute('disabled', '');

    await fetch('/auth', {
        method: 'POST', 
        body: JSON.stringify(payload), 
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(async (response) => {
        if(response.ok) {
            window.location.href = '/';
        } else {
            document.getElementById('text-error').style.display = "block";
        }
    })
    .catch(() => {
        document.getElementById('text-error').style.display = "block";
    })
    .finally(() => {
        loginBtn.removeAttribute('disabled');
    })
});

const togglePassword = document.querySelector('#togglePassword');
const password = document.querySelector('#password');

togglePassword.addEventListener('click', () => {
    const type = password.getAttribute('type') === 'password' ? 'text' : 'password';
    password.setAttribute('type', type);

    togglePassword.classList.toggle('fa-eye');
    togglePassword.classList.toggle('fa-eye-slash');
});