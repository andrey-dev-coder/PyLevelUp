from dataclasses import dataclass


@dataclass(frozen=True)
class Cheatsheet:
    key: str
    title: str
    body: str


CHEATSHEETS: tuple[Cheatsheet, ...] = (
    Cheatsheet(
        key="py_types",
        title="Python: типы данных",
        body=(
            "<b>Изменяемые (mutable):</b>\n"
            "<code>list</code>, <code>dict</code>, <code>set</code>, <code>bytearray</code>\n\n"
            "<b>Неизменяемые (immutable):</b>\n"
            "<code>int</code>, <code>float</code>, <code>str</code>, <code>tuple</code>, <code>frozenset</code>, <code>bytes</code>, <code>None</code>, <code>bool</code>\n\n"
            "<b>Особенности:</b>\n"
            "- <code>bool</code> наследник <code>int</code>: <code>True == 1</code>, <code>False == 0</code>\n"
            "- <code>tuple(1,)</code> - кортеж из 1 элемента, <code>(1)</code> - просто <code>int</code>\n"
            "- <code>{}</code> создаёт <code>dict</code>, для пустого <code>set</code> - <code>set()</code>\n"
            "- <code>None</code> единственный объект своего типа (singleton)\n\n"
            "<b>Быстрые проверки:</b>\n"
            "- <code>isinstance(x, int)</code> вместо <code>type(x) is int</code>\n"
            "- <code>is None</code> вместо <code>== None</code>\n"
            "- truthy: непустые контейнеры, ненулевые числа, не-<code>None</code>"
        ),
    ),
    Cheatsheet(
        key="py_complexity",
        title="Сложности структур",
        body=(
            "<b>list:</b>\n"
            "- <code>append</code>, <code>pop()</code>: O(1)\n"
            "- <code>insert</code>, <code>pop(0)</code>: O(n)\n"
            "- <code>x in lst</code>: O(n)\n"
            "- <code>lst[i]</code>: O(1)\n\n"
            "<b>dict / set:</b>\n"
            "- <code>get</code>, <code>__setitem__</code>, <code>in</code>: O(1) среднее\n"
            "- worst case O(n) при коллизиях\n\n"
            "<b>deque (<code>collections.deque</code>):</b>\n"
            "- <code>append</code>, <code>appendleft</code>, <code>pop</code>, <code>popleft</code>: O(1)\n"
            "- <code>deque[i]</code>: O(n) - используй только концы\n\n"
            "<b>heapq:</b>\n"
            "- <code>heappush</code>, <code>heappop</code>: O(log n)\n"
            "- <code>heapify</code>: O(n)\n\n"
            "<b>str:</b>\n"
            "- <code>s + t</code>: O(n+m), для конкатенации списка лучше <code>''.join(items)</code>\n"
            "- <code>s in t</code>: O(n*m)"
        ),
    ),
    Cheatsheet(
        key="py_gil",
        title="GIL и многопоточность",
        body=(
            "<b>GIL (Global Interpreter Lock):</b>\n"
            "- 1 поток выполняет байткод за раз в CPython\n"
            "- IO-bound: <code>threading</code> ок, GIL отпускается на IO\n"
            "- CPU-bound: <code>multiprocessing</code> или <code>concurrent.futures.ProcessPoolExecutor</code>\n"
            "- В Python 3.13 экспериментальный <code>--disable-gil</code> сборка\n\n"
            "<b>Конкурентность:</b>\n"
            "- <code>threading</code> - потоки (общая память, GIL)\n"
            "- <code>multiprocessing</code> - процессы (отдельная память, IPC через <code>Pipe</code>/<code>Queue</code>)\n"
            "- <code>asyncio</code> - корутины (1 поток, event loop)\n\n"
            "<b>asyncio:</b>\n"
            "- <code>async def</code>, <code>await</code>\n"
            "- <code>asyncio.gather(*tasks)</code> - параллельно\n"
            "- <code>asyncio.create_task(coro)</code> - запустить в фоне\n"
            "- блокирующий код в <code>loop.run_in_executor</code>"
        ),
    ),
    Cheatsheet(
        key="py_decorators",
        title="Декораторы",
        body=(
            "<b>Базовый декоратор:</b>\n"
            "<pre><code>from functools import wraps\n\n"
            "def my_decorator(func):\n"
            "    @wraps(func)\n"
            "    def wrapper(*args, **kwargs):\n"
            "        return func(*args, **kwargs)\n"
            "    return wrapper</code></pre>\n\n"
            "<b>С параметрами:</b>\n"
            "<pre><code>def repeat(n):\n"
            "    def decorator(func):\n"
            "        @wraps(func)\n"
            "        def wrapper(*args, **kwargs):\n"
            "            for _ in range(n):\n"
            "                result = func(*args, **kwargs)\n"
            "            return result\n"
            "        return wrapper\n"
            "    return decorator</code></pre>\n\n"
            "<b>Встроенные:</b>\n"
            "- <code>@staticmethod</code>, <code>@classmethod</code>, <code>@property</code>\n"
            "- <code>@functools.lru_cache</code>, <code>@functools.cache</code>\n"
            "- <code>@dataclass</code>, <code>@contextmanager</code>\n\n"
            "<b>Зачем <code>@wraps</code>?</b>\n"
            "Сохраняет <code>__name__</code>, <code>__doc__</code>, <code>__wrapped__</code> исходной функции."
        ),
    ),
    Cheatsheet(
        key="sql",
        title="SQL: команды",
        body=(
            "<b>SELECT с JOIN:</b>\n"
            "<code>SELECT u.name, COUNT(o.id) FROM users u "
            "LEFT JOIN orders o ON o.user_id = u.id "
            "GROUP BY u.id HAVING COUNT(o.id) > 5 ORDER BY u.name LIMIT 10;</code>\n\n"
            "<b>JOIN типы:</b>\n"
            "- <code>INNER JOIN</code> - только совпадения\n"
            "- <code>LEFT JOIN</code> - все слева + совпадения справа\n"
            "- <code>FULL OUTER JOIN</code> - все с обеих сторон\n"
            "- <code>CROSS JOIN</code> - декартово произведение\n\n"
            "<b>Оконные функции:</b>\n"
            "- <code>ROW_NUMBER() OVER (PARTITION BY x ORDER BY y)</code>\n"
            "- <code>RANK()</code>, <code>DENSE_RANK()</code>\n"
            "- <code>LAG(col, 1)</code>, <code>LEAD(col, 1)</code>\n"
            "- <code>SUM(x) OVER (ORDER BY y ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)</code>\n\n"
            "<b>UPSERT (PostgreSQL):</b>\n"
            "<code>INSERT INTO t(id, x) VALUES (1, 'a') ON CONFLICT (id) DO UPDATE SET x = EXCLUDED.x;</code>\n\n"
            "<b>Индексы:</b>\n"
            "- B-tree (дефолт) - для <code>=</code>, <code>&lt;</code>, <code>&gt;</code>, <code>BETWEEN</code>\n"
            "- Hash - только <code>=</code>\n"
            "- GIN - JSONB, массивы, full-text search\n"
            "- GiST - геометрия, диапазоны"
        ),
    ),
    Cheatsheet(
        key="sql_isolation",
        title="SQL: уровни изоляции",
        body=(
            "<b>4 уровня (от слабого к сильному):</b>\n\n"
            "<b>READ UNCOMMITTED</b> - читает незакоммиченное (dirty read)\n"
            "<b>READ COMMITTED</b> - только закоммиченное (дефолт PostgreSQL)\n"
            "<b>REPEATABLE READ</b> - тот же запрос вернёт то же (snapshot)\n"
            "<b>SERIALIZABLE</b> - как если бы транзакции шли последовательно\n\n"
            "<b>Аномалии:</b>\n"
            "- Dirty Read - чтение незакоммиченных данных\n"
            "- Non-Repeatable Read - одна строка прочитана дважды, второй раз изменилась\n"
            "- Phantom Read - повторный <code>SELECT</code> вернул новые строки\n"
            "- Lost Update - две транзакции перезаписали друг друга\n"
            "- Serialization Anomaly - последовательность транзакций не воспроизводима\n\n"
            "<b>В Django:</b>\n"
            "<code>transaction.atomic()</code> - стандартная транзакция\n"
            "<code>select_for_update()</code> - блокировка строк"
        ),
    ),
    Cheatsheet(
        key="http",
        title="HTTP: статусы",
        body=(
            "<b>1xx Informational</b>\n"
            "- 100 Continue, 101 Switching Protocols\n\n"
            "<b>2xx Success</b>\n"
            "- 200 OK\n"
            "- 201 Created (после успешного POST)\n"
            "- 202 Accepted (асинхронно принято)\n"
            "- 204 No Content (например после DELETE)\n\n"
            "<b>3xx Redirection</b>\n"
            "- 301 Moved Permanently\n"
            "- 302 Found (временно)\n"
            "- 304 Not Modified (для кеша)\n\n"
            "<b>4xx Client Error</b>\n"
            "- 400 Bad Request\n"
            "- 401 Unauthorized (нужна аутентификация)\n"
            "- 403 Forbidden (нет прав)\n"
            "- 404 Not Found\n"
            "- 409 Conflict (дубликат, версии)\n"
            "- 422 Unprocessable Entity (валидация)\n"
            "- 429 Too Many Requests\n\n"
            "<b>5xx Server Error</b>\n"
            "- 500 Internal Server Error\n"
            "- 502 Bad Gateway\n"
            "- 503 Service Unavailable\n"
            "- 504 Gateway Timeout"
        ),
    ),
    Cheatsheet(
        key="http_methods",
        title="HTTP: методы и идемпотентность",
        body=(
            "<b>Идемпотентные</b> (повтор не меняет результат):\n"
            "<code>GET</code>, <code>HEAD</code>, <code>PUT</code>, <code>DELETE</code>, <code>OPTIONS</code>\n\n"
            "<b>Не идемпотентные:</b>\n"
            "<code>POST</code>, <code>PATCH</code>\n\n"
            "<b>Безопасные</b> (не меняют состояние):\n"
            "<code>GET</code>, <code>HEAD</code>, <code>OPTIONS</code>\n\n"
            "<b>Семантика:</b>\n"
            "- <code>GET</code> - чтение\n"
            "- <code>POST</code> - создание (без указания ID)\n"
            "- <code>PUT</code> - полная замена ресурса\n"
            "- <code>PATCH</code> - частичное обновление\n"
            "- <code>DELETE</code> - удаление\n\n"
            "<b>Кеширование:</b>\n"
            "- <code>Cache-Control: max-age=3600</code>\n"
            "- <code>ETag</code> + <code>If-None-Match</code> - условный GET\n"
            "- <code>Last-Modified</code> + <code>If-Modified-Since</code>"
        ),
    ),
    Cheatsheet(
        key="git",
        title="Git: команды",
        body=(
            "<b>Базовое:</b>\n"
            "<code>git status</code>, <code>git diff</code>, <code>git log --oneline --graph</code>\n"
            "<code>git add -p</code> (по кускам), <code>git commit -m 'msg'</code>\n\n"
            "<b>Ветки:</b>\n"
            "<code>git checkout -b feat/x</code>\n"
            "<code>git switch main</code>\n"
            "<code>git branch -d feat/x</code>\n\n"
            "<b>Слияние:</b>\n"
            "<code>git merge feat/x</code> - merge commit\n"
            "<code>git rebase main</code> - переписать поверх main\n"
            "<code>git cherry-pick &lt;sha&gt;</code> - взять конкретный коммит\n\n"
            "<b>Откат:</b>\n"
            "<code>git restore --staged file</code> - убрать из stage\n"
            "<code>git restore file</code> - откатить изменения файла\n"
            "<code>git reset --soft HEAD~1</code> - отменить коммит, оставить изменения\n"
            "<code>git reset --hard HEAD~1</code> - отменить коммит и изменения (опасно)\n"
            "<code>git revert &lt;sha&gt;</code> - новый коммит, отменяющий старый\n\n"
            "<b>Удалёнка:</b>\n"
            "<code>git fetch</code>, <code>git pull --rebase</code>, <code>git push --force-with-lease</code>"
        ),
    ),
    Cheatsheet(
        key="docker",
        title="Docker: команды",
        body=(
            "<b>Образы:</b>\n"
            "<code>docker build -t myapp:v1 .</code>\n"
            "<code>docker images</code>, <code>docker rmi &lt;img&gt;</code>\n\n"
            "<b>Контейнеры:</b>\n"
            "<code>docker run -d -p 8000:8000 --name app myapp:v1</code>\n"
            "<code>docker ps</code> / <code>docker ps -a</code>\n"
            "<code>docker exec -it app bash</code>\n"
            "<code>docker logs -f app</code>\n"
            "<code>docker stop app</code>, <code>docker rm app</code>\n\n"
            "<b>Тома:</b>\n"
            "<code>docker run -v /host/path:/container/path</code>\n"
            "<code>docker volume create vol1</code>\n\n"
            "<b>docker-compose:</b>\n"
            "<code>docker compose up -d</code>\n"
            "<code>docker compose down -v</code>\n"
            "<code>docker compose exec service-name bash</code>\n\n"
            "<b>Очистка:</b>\n"
            "<code>docker system prune -a --volumes</code>"
        ),
    ),
    Cheatsheet(
        key="linux",
        title="Linux: команды",
        body=(
            "<b>Процессы:</b>\n"
            "<code>ps aux | grep python</code>, <code>top</code>, <code>htop</code>\n"
            "<code>kill -9 &lt;pid&gt;</code>, <code>killall python</code>\n\n"
            "<b>Файлы:</b>\n"
            "<code>find / -name '*.log' -mtime -1</code>\n"
            "<code>grep -rn 'pattern' src/</code>\n"
            "<code>tail -f /var/log/syslog</code>\n"
            "<code>du -sh ./*</code>, <code>df -h</code>\n\n"
            "<b>Сеть:</b>\n"
            "<code>netstat -tulpn</code> / <code>ss -tulpn</code>\n"
            "<code>curl -I https://example.com</code>\n"
            "<code>dig +short example.com</code>\n"
            "<code>nc -zv host 443</code> - проверка порта\n\n"
            "<b>Архивы:</b>\n"
            "<code>tar -czf x.tar.gz dir/</code>\n"
            "<code>tar -xzf x.tar.gz</code>\n\n"
            "<b>Права:</b>\n"
            "<code>chmod 755 script.sh</code>\n"
            "<code>chown -R user:group dir/</code>"
        ),
    ),
    Cheatsheet(
        key="redis",
        title="Redis: команды",
        body=(
            "<b>Строки:</b>\n"
            "<code>SET key value EX 60</code> - с TTL 60 сек\n"
            "<code>GET key</code>, <code>DEL key</code>, <code>EXPIRE key 30</code>\n"
            "<code>INCR counter</code>, <code>INCRBY counter 5</code>\n\n"
            "<b>Хеши:</b>\n"
            "<code>HSET user:1 name 'Andrey' age 30</code>\n"
            "<code>HGET user:1 name</code>, <code>HGETALL user:1</code>\n\n"
            "<b>Списки:</b>\n"
            "<code>LPUSH q msg</code>, <code>RPOP q</code>\n"
            "<code>BLPOP q 0</code> - блокирующий pop (для очередей)\n\n"
            "<b>Множества:</b>\n"
            "<code>SADD users 1 2 3</code>\n"
            "<code>SMEMBERS users</code>, <code>SINTER users:a users:b</code>\n\n"
            "<b>Sorted Sets:</b>\n"
            "<code>ZADD board 100 user1 200 user2</code>\n"
            "<code>ZRANGE board 0 9 REV WITHSCORES</code> - топ 10\n\n"
            "<b>Pub/Sub:</b>\n"
            "<code>PUBLISH channel msg</code>, <code>SUBSCRIBE channel</code>\n\n"
            "<b>Эвикция:</b>\n"
            "<code>maxmemory-policy allkeys-lru</code>"
        ),
    ),
    Cheatsheet(
        key="dunder",
        title="Python: dunder методы",
        body=(
            "<b>Конструкция:</b>\n"
            "<code>__new__(cls, *args)</code> - создание объекта (до <code>__init__</code>)\n"
            "<code>__init__(self, *args)</code> - инициализация\n"
            "<code>__del__(self)</code> - финализатор (не гарантирован)\n\n"
            "<b>Представление:</b>\n"
            "<code>__repr__</code> - однозначное (для разработчика, <code>repr(x)</code>)\n"
            "<code>__str__</code> - для пользователя (<code>str(x)</code>, <code>print</code>)\n"
            "<code>__format__</code> - <code>f'{x:spec}'</code>\n\n"
            "<b>Сравнение:</b>\n"
            "<code>__eq__</code>, <code>__lt__</code>, <code>__le__</code>, <code>__gt__</code>, <code>__ge__</code>\n"
            "<code>@functools.total_ordering</code> - заполняет недостающие\n\n"
            "<b>Контейнер:</b>\n"
            "<code>__len__</code>, <code>__contains__</code>, <code>__getitem__</code>, <code>__setitem__</code>, <code>__delitem__</code>, <code>__iter__</code>, <code>__next__</code>\n\n"
            "<b>Контекстный менеджер:</b>\n"
            "<code>__enter__</code>, <code>__exit__(exc_type, exc_val, exc_tb)</code>\n\n"
            "<b>Дескрипторы:</b>\n"
            "<code>__get__</code>, <code>__set__</code>, <code>__delete__</code>\n\n"
            "<b>Хэш и копирование:</b>\n"
            "<code>__hash__</code>, <code>__copy__</code>, <code>__deepcopy__</code>"
        ),
    ),
    Cheatsheet(
        key="python_async",
        title="Asyncio: паттерны",
        body=(
            "<b>Запуск:</b>\n"
            "<code>asyncio.run(main())</code> - точка входа\n\n"
            "<b>Параллельно:</b>\n"
            "<pre><code>results = await asyncio.gather(\n"
            "    fetch(a), fetch(b), fetch(c),\n"
            "    return_exceptions=True,\n"
            ")</code></pre>\n\n"
            "<b>Фоновая задача:</b>\n"
            "<code>task = asyncio.create_task(coro())</code>\n"
            "<code>await task</code>\n"
            "<code>task.cancel()</code>\n\n"
            "<b>Таймаут:</b>\n"
            "<pre><code>async with asyncio.timeout(5):\n"
            "    await slow_op()</code></pre>\n\n"
            "<b>Семафор / лимит:</b>\n"
            "<pre><code>sem = asyncio.Semaphore(10)\n"
            "async with sem:\n"
            "    await op()</code></pre>\n\n"
            "<b>Блокирующий код:</b>\n"
            "<code>await asyncio.to_thread(sync_func, *args)</code>\n\n"
            "<b>Очереди:</b>\n"
            "<code>q = asyncio.Queue(maxsize=100)</code>\n"
            "<code>await q.put(x)</code>, <code>x = await q.get()</code>"
        ),
    ),
)


def get_cheatsheet(key: str) -> Cheatsheet | None:
    for sheet in CHEATSHEETS:
        if sheet.key == key:
            return sheet
    return None


__all__ = ["Cheatsheet", "CHEATSHEETS", "get_cheatsheet"]
