"""Create a separate administrator account for the configured database."""

from getpass import getpass

from database.connection import session_scope
from services.auth_service import AuthenticationError, register_admin_user


def main() -> None:
    name = input("Nome do administrador: ").strip()
    email = input("E-mail do administrador: ").strip()
    password = getpass("Senha (mínimo de 10 caracteres): ")
    confirmation = getpass("Confirme a senha: ")

    if password != confirmation:
        raise SystemExit("As senhas não conferem.")

    try:
        with session_scope() as session:
            register_admin_user(session, name, email, password)
    except AuthenticationError as exc:
        raise SystemExit(str(exc)) from exc

    print("Conta admin criada com sucesso.")


if __name__ == "__main__":
    main()