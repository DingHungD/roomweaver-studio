"""Application-only SQLite migrations; LangGraph owns its separate database."""
def migrate(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS studio_schema (version INTEGER PRIMARY KEY)')
    row=connection.execute('SELECT max(version) FROM studio_schema').fetchone()
    version=row[0] or 0
    if version>2:
        raise ValueError('Studio 資料庫版本較新，請使用相容的應用程式')
    if version<1:
        connection.executescript('''CREATE TABLE IF NOT EXISTS studio_revisions (
            project_id TEXT, revision TEXT PRIMARY KEY, created_at TEXT, path TEXT);
            CREATE TABLE IF NOT EXISTS studio_operations (
            id TEXT PRIMARY KEY, project_id TEXT, fingerprint TEXT, job_id TEXT);
            CREATE TABLE IF NOT EXISTS studio_workflows (
            id TEXT PRIMARY KEY, project_id TEXT, operation_id TEXT UNIQUE, data TEXT);
            INSERT INTO studio_schema VALUES (1);''')
    if version<2:
        connection.executescript('''CREATE TABLE IF NOT EXISTS studio_output_trash (
            project_id TEXT NOT NULL, job_id TEXT NOT NULL, deleted_at TEXT NOT NULL,
            PRIMARY KEY(project_id, job_id));
            INSERT INTO studio_schema VALUES (2);''')
