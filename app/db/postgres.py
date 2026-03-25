from __future__ import annotations

from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from app.constants import app as app_constants


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_git_username(value: Any) -> str | None:
    username = _normalize_optional_text(value)
    if username is None:
        return None
    return username.lower()


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        '''
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        ''',
        (table_name,),
    )
    return cursor.fetchone() is not None


def _table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(
        '''
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ''',
        (table_name,),
    )
    return {row[0] for row in cursor.fetchall()}


def _column_has_unique_or_primary_constraint(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        '''
        SELECT 1
        FROM information_schema.table_constraints tc
        INNER JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND kcu.column_name = %s
          AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        ''',
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def _create_users_table(cursor) -> None:
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            git_username VARCHAR(255) PRIMARY KEY,
            id BIGINT UNIQUE,
            email TEXT
        )
        '''
    )
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_id ON users (id)')


def _create_roles_table(cursor) -> None:
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS roles (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(64) NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        '''
    )
    cursor.executemany(
        '''
        INSERT INTO roles (name, description)
        VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE
        SET description = EXCLUDED.description
        ''',
        [
            (app_constants.DEFAULT_ROLE_USER, 'Default application user role'),
            (app_constants.DEFAULT_ROLE_ADMIN, 'Administrative role'),
        ],
    )


def _create_user_roles_table(cursor) -> None:
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS user_roles (
            git_username VARCHAR(255) NOT NULL REFERENCES users(git_username) ON DELETE CASCADE,
            role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (git_username, role_id)
        )
        '''
    )


def _migrate_users_table_if_required(cursor) -> None:
    if not _table_exists(cursor, 'users'):
        _create_users_table(cursor)
        return

    columns = _table_columns(cursor, 'users')
    target_columns = {'git_username', 'id', 'email'}
    git_username_is_unique = _column_has_unique_or_primary_constraint(cursor, 'users', 'git_username')
    if columns == target_columns and git_username_is_unique:
        return

    select_columns = []
    for column_name in ('id', 'github_id', 'git_username', 'login', 'email'):
        if column_name in columns:
            select_columns.append(column_name)

    if 'id' not in select_columns:
        raise RuntimeError('Cannot migrate users table: missing required id column.')

    old_users: list[dict[str, Any]]
    old_user_roles: list[dict[str, Any]] = []
    users_by_username: dict[str, dict[str, Any]] = {}
    old_id_to_username: dict[int, str] = {}

    with cursor.connection.cursor(row_factory=dict_row) as dict_cursor:
        dict_cursor.execute(f"SELECT {', '.join(select_columns)} FROM users")
        old_users = list(dict_cursor.fetchall())

        if _table_exists(cursor, 'user_roles'):
            role_columns = _table_columns(cursor, 'user_roles')
            if {'user_id', 'role_id'}.issubset(role_columns):
                dict_cursor.execute('SELECT user_id, role_id FROM user_roles')
                old_user_roles = list(dict_cursor.fetchall())
            elif {'git_username', 'role_id'}.issubset(role_columns):
                dict_cursor.execute('SELECT git_username, role_id FROM user_roles')
                old_user_roles = list(dict_cursor.fetchall())

    for old_user in old_users:
        git_username = _normalize_git_username(old_user.get('git_username')) or _normalize_git_username(
            old_user.get('login')
        )
        if git_username is None:
            continue

        github_id_raw = old_user.get('github_id')
        id_raw = old_user.get('id')
        selected_id_raw = github_id_raw if github_id_raw is not None else id_raw
        migrated_id = None
        if selected_id_raw is not None:
            try:
                migrated_id = int(selected_id_raw)
            except (TypeError, ValueError):
                migrated_id = None

        email = _normalize_optional_text(old_user.get('email'))

        users_by_username[git_username] = {
            'git_username': git_username,
            'id': migrated_id,
            'email': email,
        }

        if id_raw is not None:
            try:
                old_id_to_username[int(id_raw)] = git_username
            except (TypeError, ValueError):
                pass

    migrated_roles: set[tuple[str, int]] = set()
    for user_role in old_user_roles:
        role_id_raw = user_role.get('role_id')
        if role_id_raw is None:
            continue
        try:
            role_id = int(role_id_raw)
        except (TypeError, ValueError):
            continue

        role_username = _normalize_git_username(user_role.get('git_username'))
        if role_username is None:
            old_user_id_raw = user_role.get('user_id')
            if old_user_id_raw is None:
                continue
            try:
                old_user_id = int(old_user_id_raw)
            except (TypeError, ValueError):
                continue
            role_username = old_id_to_username.get(old_user_id)

        if role_username is None:
            continue
        migrated_roles.add((role_username, role_id))

    cursor.execute('DROP TABLE IF EXISTS user_roles')
    cursor.execute('DROP TABLE users')

    _create_users_table(cursor)
    if users_by_username:
        cursor.executemany(
            'INSERT INTO users (git_username, id, email) VALUES (%s, %s, %s)',
            [
                (user_data['git_username'], user_data['id'], user_data['email'])
                for user_data in users_by_username.values()
            ],
        )

    _create_user_roles_table(cursor)
    if migrated_roles:
        cursor.executemany(
            '''
            INSERT INTO user_roles (git_username, role_id)
            VALUES (%s, %s)
            ON CONFLICT (git_username, role_id) DO NOTHING
            ''',
            list(migrated_roles),
        )

    print('PostgreSQL users schema migrated to columns: git_username, id, email.')


def verify_postgres_connection(postgres_dsn: str) -> None:
    dsn = (postgres_dsn or '').strip()
    if not dsn:
        print('PostgreSQL connection skipped: postgres_dsn is not configured.')
        return

    try:
        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()

            print(
                'PostgreSQL connection successful '
                f"(host={connection.info.host} port={connection.info.port} "
                f"dbname={connection.info.dbname} user={connection.info.user})"
            )
    except Exception as error:
        raise RuntimeError(f'PostgreSQL connection failed: {error}') from error


def ensure_auth_tables(postgres_dsn: str) -> None:
    dsn = (postgres_dsn or '').strip()
    if not dsn:
        raise RuntimeError('PostgreSQL schema initialization failed: postgres_dsn is not configured.')

    try:
        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                _create_roles_table(cursor)
                _migrate_users_table_if_required(cursor)
                _create_user_roles_table(cursor)
            connection.commit()

        print('PostgreSQL auth schema ready (users, roles, user_roles).')
    except Exception as error:
        raise RuntimeError(f'PostgreSQL schema initialization failed: {error}') from error


def _assign_default_roles(cursor, git_username: str) -> None:
    for role_name in (app_constants.DEFAULT_ROLE_ADMIN, app_constants.DEFAULT_ROLE_USER):
        cursor.execute(
            '''
            INSERT INTO user_roles (git_username, role_id)
            SELECT %s, id
            FROM roles
            WHERE name = %s
            ON CONFLICT (git_username, role_id) DO NOTHING
            ''',
            (git_username, role_name),
        )


def ensure_bootstrap_admin_user(postgres_dsn: str) -> None:
    dsn = (postgres_dsn or '').strip()
    if not dsn:
        raise RuntimeError('Bootstrap admin initialization failed: postgres_dsn is not configured.')

    bootstrap_username = _normalize_git_username(app_constants.BOOTSTRAP_ADMIN_LOGIN)
    if bootstrap_username is None:
        raise RuntimeError('Bootstrap admin initialization failed: invalid bootstrap username.')

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO users (git_username, id, email)
                VALUES (%s, %s, %s)
                ON CONFLICT (git_username) DO UPDATE SET
                    id = EXCLUDED.id,
                    email = EXCLUDED.email
                ''',
                (
                    bootstrap_username,
                    app_constants.BOOTSTRAP_ADMIN_GITHUB_ID,
                    app_constants.BOOTSTRAP_ADMIN_EMAIL,
                ),
            )
            _assign_default_roles(cursor, bootstrap_username)
        connection.commit()

    print(
        'Bootstrap admin user ensured '
        f"(id={app_constants.BOOTSTRAP_ADMIN_GITHUB_ID}, git_username={bootstrap_username})."
    )


def _session_user_from_row(user_row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        app_constants.SESSION_USER_FIELD_ID: int(user_row['id']) if user_row['id'] is not None else None,
        app_constants.SESSION_USER_FIELD_LOGIN: str(user_row['git_username']),
        app_constants.GITHUB_EMAIL_FIELD_EMAIL: user_row['email'],
    }


def is_admin_user(postgres_dsn: str, git_username: str) -> bool:
    dsn = (postgres_dsn or '').strip()
    normalized_username = _normalize_git_username(git_username)
    if not dsn or normalized_username is None:
        return False

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                '''
                SELECT 1
                FROM user_roles ur
                INNER JOIN roles r ON r.id = ur.role_id
                WHERE ur.git_username = %s AND r.name = %s
                ''',
                (normalized_username, app_constants.DEFAULT_ROLE_ADMIN),
            )
            return cursor.fetchone() is not None


def allowed_user_exists(postgres_dsn: str, git_username: str) -> bool:
    dsn = (postgres_dsn or '').strip()
    normalized_username = _normalize_git_username(git_username)
    if not dsn or normalized_username is None:
        return False

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                '''
                SELECT 1
                FROM users
                WHERE git_username = %s
                ''',
                (normalized_username,),
            )
            return cursor.fetchone() is not None


def add_allowed_user(postgres_dsn: str, git_username: str, email: str | None = None) -> dict[str, Any]:
    dsn = (postgres_dsn or '').strip()
    normalized_username = _normalize_git_username(git_username)
    if not dsn:
        raise RuntimeError('postgres_dsn is not configured.')
    if normalized_username is None:
        raise ValueError('git_username is required.')

    normalized_email = _normalize_optional_text(email)
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO users (git_username, email)
                VALUES (%s, %s)
                ON CONFLICT (git_username) DO UPDATE SET
                    email = COALESCE(EXCLUDED.email, users.email)
                RETURNING git_username, id, email
                ''',
                (normalized_username, normalized_email),
            )
            user_row = cursor.fetchone()
            if not user_row:
                raise RuntimeError('User provisioning returned no row.')

            cursor.execute(
                '''
                INSERT INTO user_roles (git_username, role_id)
                SELECT %s, id
                FROM roles
                WHERE name = %s
                ON CONFLICT (git_username, role_id) DO NOTHING
                ''',
                (normalized_username, app_constants.DEFAULT_ROLE_USER),
            )
        connection.commit()

    return _session_user_from_row(user_row)


def authorize_existing_github_user(
    postgres_dsn: str,
    github_user: Mapping[str, Any],
    email: str | None,
) -> dict[str, Any]:
    dsn = (postgres_dsn or '').strip()
    if not dsn:
        raise RuntimeError('postgres_dsn is not configured.')

    github_id_raw = github_user.get(app_constants.GITHUB_USER_FIELD_ID)
    git_username = _normalize_git_username(github_user.get(app_constants.GITHUB_USER_FIELD_LOGIN))
    if github_id_raw is None:
        raise ValueError('GitHub user id is missing from OAuth response.')
    if git_username is None:
        raise ValueError('GitHub login is missing from OAuth response.')

    try:
        github_id = int(github_id_raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f'Invalid GitHub user id value: {github_id_raw!r}') from error

    normalized_email = _normalize_optional_text(email)

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                '''
                SELECT git_username, id
                FROM users
                WHERE git_username = %s
                ''',
                (git_username,),
            )
            existing_user = cursor.fetchone()
            if not existing_user:
                raise PermissionError(f'Git username {git_username} is not provisioned.')

            existing_id = existing_user['id']
            if existing_id is not None and int(existing_id) != github_id:
                raise PermissionError(f'Git username {git_username} is mapped to a different id.')

            cursor.execute(
                '''
                UPDATE users
                SET
                    id = COALESCE(id, %s),
                    email = %s
                WHERE git_username = %s
                RETURNING git_username, id, email
                ''',
                (github_id, normalized_email, git_username),
            )
            user_row = cursor.fetchone()
            if not user_row:
                raise RuntimeError('Provisioned user update returned no row.')

            cursor.execute(
                '''
                INSERT INTO user_roles (git_username, role_id)
                SELECT %s, id
                FROM roles
                WHERE name = %s
                ON CONFLICT (git_username, role_id) DO NOTHING
                ''',
                (git_username, app_constants.DEFAULT_ROLE_USER),
            )
        connection.commit()

    return _session_user_from_row(user_row)
