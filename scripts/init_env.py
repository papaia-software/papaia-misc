"""Generate local secrets once. Never overwrite an existing .env."""
from pathlib import Path
import secrets
import getpass

root=Path(__file__).resolve().parent.parent
path=root/'.env'
if path.exists():
    raise SystemExit('.env já existe; arquivo preservado. Edite suas configurações manualmente.')
password=getpass.getpass('Defina ADMIN_PASSWORD (mínimo 12 caracteres): ')
if len(password)<12 or any(c in password for c in '\n\r\x00'):
    raise SystemExit('Senha inválida; mínimo de 12 caracteres.')
# dotenv single-quoted string; escaped slashes and quotes preserve user input.
quoted="'"+password.replace('\\','\\\\').replace("'","\\'")+"'"
content=(root/'.env.example').read_text().replace('SECRET_KEY=\n','SECRET_KEY='+secrets.token_urlsafe(48)+'\n').replace('ADMIN_PASSWORD=\n','ADMIN_PASSWORD='+quoted+'\n')
path.write_text(content)
path.chmod(0o600)
print('.env criado com segredos locais. Usuário: admin@papaia.local')
