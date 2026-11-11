"""Russian and English text for the schema-backed settings editor."""
from .i18n import language

UI = {
    "title": ("OpenCode settings", "Настройки OpenCode"), "mcp": ("MCP servers", "Серверы MCP"),
    "mcpToggle": ("Enable or disable this server. Changes take effect after Save.", "Включить или выключить сервер. Изменения применяются после сохранения."),
    "timeouts": ("Connection timeouts", "Лимиты времени подключения"),
    "timeoutsHint": ("Expand or collapse global MCP timeouts. Each server can override them.", "Развернуть или свернуть общие тайм-ауты MCP. Каждый сервер может переопределить их."),
    "subtitle": ("OpenCode {version} schema · global configuration · {count} fields", "Схема OpenCode {version} · глобальная конфигурация · {count} параметров"),
    "search": ("Search settings, descriptions or configuration keys", "Поиск по настройкам, описаниям и ключам конфига"),
    "inherit": ("Not set (inherit)", "Не задано (наследовать)"),
    "set": ("Set value", "Задать значение"), "on": ("Enabled", "Включено"), "off": ("Disabled", "Выключено"),
    "string": ("Text", "Текст"), "number": ("Number", "Число"), "integer": ("Integer", "Целое число"),
    "object": ("Configure fields", "Настроить поля"), "array": ("Configure list", "Настроить список"),
    "json": ("Custom JSON value", "Произвольное значение JSON"), "null": ("Empty (null)", "Пусто (null)"),
    "edit": ("Edit…", "Изменить…"), "add": ("Add", "Добавить"), "remove": ("Remove", "Удалить"),
    "up": ("Move up", "Выше"), "down": ("Move down", "Ниже"), "cancel": ("Cancel", "Отмена"),
    "apply": ("Apply to draft", "Внести в черновик"), "save": ("Save", "Сохранить"),
    "discard": ("Discard changes", "Отменить изменения"), "refresh": ("Refresh", "Обновить"),
    "reset": ("Reset config", "Сбросить конфиг"),
    "resetTitle": ("Reset the configuration?", "Сбросить конфигурацию?"),
    "resetConfirm": ("Replace {file} with an empty config? The current file is kept beside it as a backup first. "
                     "opencode falls back to its defaults, and every setting this file holds goes with it — "
                     "the way out when the file and the editors cannot agree.",
                     "Заменить {file} пустым конфигом? Текущий файл сначала сохранится рядом как резервная копия. "
                     "opencode вернётся к настройкам по умолчанию, и все настройки этого файла уйдут вместе с ним — "
                     "выход, когда файл и редакторы не могут договориться."),
    "all": ("All settings", "Все настройки"), "general": ("General", "Основные"),
    "models": ("Models and providers", "Модели и провайдеры"), "agents": ("Agents and commands", "Агенты и команды"),
    "context": ("Context and limits", "Контекст и лимиты"), "workspace": ("Files and development", "Файлы и разработка"),
    "sources": ("Instructions and sources", "Инструкции и источники"),
    "integrations": ("Plugins and web search", "Плагины и веб-поиск"),
    "permissions": ("Permissions and policies", "Разрешения и политики"),
    "experimental": ("Experimental", "Экспериментальные"),
    "inheritHint": ("No value is written to this file. OpenCode inherits another configuration value or its own default.",
                    "Значение не записывается в этот файл. OpenCode наследует его из другой конфигурации либо использует своё значение по умолчанию."),
    "scope": ("Project and managed settings can override this file. Changes are written only after Save.",
              "Настройки проекта и управляемые политики могут переопределить этот файл. Изменения записываются только по кнопке «Сохранить»."),
    "pending": ("Unsaved changes: {count}", "Несохранённых изменений: {count}"),
    "clean": ("No unsaved changes", "Нет несохранённых изменений"),
    "saved": ("Saved. Changed files are backed up before replacement.", "Сохранено. Перед изменением файла создаётся резервная копия."),
    "external": ("The file changed outside this editor. Your draft is retained; saving merges unrelated changes and checks conflicts.",
                 "Файл изменён вне редактора. Черновик сохранён; запись объединит независимые изменения и проверит конфликты."),
    "conflict": ("Not saved: this setting was changed elsewhere: {error}. Refresh after resolving the conflict.",
                 "Не сохранено: этот параметр уже изменён вне редактора: {error}. Разрешите конфликт и обновите данные."),
    "invalid": ("Invalid setting: {error}", "Недопустимое значение: {error}"),
    "failed": ("Could not save: {error}", "Не удалось сохранить: {error}"),
    "required": ("Required", "Обязательное поле"),
    "key": ("Name / identifier", "Имя / идентификатор"),
    "duplicate": ("Use a non-empty, unique name.", "Укажите непустое уникальное имя."),
    "empty": ("No items", "Нет записей"), "items": ("Items: {count}", "Записей: {count}"),
    "extras": ("Additional fields", "Дополнительные поля"),
    "customHint": ("Provider or plugin-specific JSON data. Its structure is defined by that integration.",
                   "Данные JSON, специфичные для провайдера или плагина. Их структуру определяет соответствующая интеграция."),
    "order": ("Order is preserved. For permission rules the last matching rule wins.",
              "Порядок сохраняется. Для правил разрешений действует последнее совпавшее правило."),
    "session": ("Applies when selecting an agent/model or starting a new session; existing sessions keep their selection.",
                "Применяется при выборе агента/модели или создании новой сессии; существующие сессии сохраняют свой выбор."),
    "terminal": ("New terminals and shell executions use the new shell. Already running processes are unchanged.",
                 "Новая оболочка используется для новых терминалов и запусков команд. Уже работающие процессы не меняются."),
    "services": ("OpenCode reloads configuration. Existing integration processes may need reconnection or a workspace reload; third-party plugins can require a restart.",
                 "OpenCode перечитывает конфигурацию. Действующим процессам интеграций может понадобиться переподключение или перезагрузка рабочего пространства; сторонние плагины могут требовать перезапуска."),
    "live": ("OpenCode watches this file. The setting is used by subsequent operations after it reloads the configuration.",
             "OpenCode следит за этим файлом. После перечитывания настройка используется в последующих операциях."),
    "applyNotice": ("When changes take effect", "Когда применятся изменения"),
    "quit": ("There are unsaved settings. Discard them and quit OpenCode Companion?", "В настройках есть несохранённые изменения. Отменить их и выйти из OpenCode Companion?"),
    "resetQuestion": ("Discard unsaved changes in this tab?", "Отменить несохранённые изменения на этой вкладке?"),
}

# key aliases | English label | Russian label | English help | Russian help
_FIELDS = """
bash|Shell access|Доступ к оболочке|Permission to execute shell commands.|Разрешение выполнять команды оболочки.
build,plan,general,explore,summary|Built-in agent|Встроенный агент|Override settings for this built-in agent.|Переопределение настроек этого встроенного агента.
doom_loop|Repeated tool calls|Повторение вызовов|Permission for repeated identical tool calls.|Разрешение повторять одинаковые вызовы инструментов.
edit,write|Write files|Запись файлов|Permission to create or modify files.|Разрешение создавать и изменять файлы.
external_directory|External directories|Внешние каталоги|Permission to access files outside the workspace.|Разрешение доступа к файлам за пределами рабочего пространства.
glob,grep,list,read|Read and search files|Чтение и поиск файлов|Permission to read or search files using this tool.|Разрешение читать или искать файлы этим инструментом.
question|Ask questions|Задавать вопросы|Permission to ask the user questions.|Разрешение задавать вопросы пользователю.
skill|Load skills|Загрузка навыков|Permission to load skill instructions.|Разрешение загружать инструкции навыков.
task|Delegate tasks|Делегирование задач|Permission to delegate work to subagents.|Разрешение передавать работу сабагентам.
todowrite|Task list|Список задач|Permission to update the task list.|Разрешение изменять список задач.
toggle|Toggle|Переключатель|Enable or disable this feature.|Включение или выключение этой функции.
webfetch|Fetch web pages|Загрузка веб-страниц|Permission to retrieve web pages.|Разрешение загружать веб-страницы.
$schema|Schema address|Адрес схемы|Schema used by configuration editors.|Схема проверки и автодополнения конфигурации.
shell|Command shell|Командная оболочка|Executable used for new terminals and shell commands.|Путь к оболочке для новых терминалов и команд.
model,small_model|Model|Модель|Model reference in provider/model format; agents and commands can specify #variant.|Ссылка provider/model; агенты и команды могут также указать #вариант.
default_agent|Default agent|Агент по умолчанию|Primary agent used when a session has no agent selected.|Основной агент для сессий, в которых агент ещё не выбран.
update,autoupdate|Updates|Обновления|How OpenCode checks and installs updates.|Режим проверки и установки обновлений OpenCode.
share,autoshare|Session sharing|Публикация сессий|Whether and how sessions may be shared by link.|Разрешение и режим публикации сессий по ссылке.
enterprise|Enterprise service|Корпоративный сервис|Enterprise sharing service connection.|Подключение к корпоративному сервису публикации.
username|User name|Имя пользователя|Name displayed in conversations and telemetry identity.|Имя в разговорах и идентификатор телеметрии.
permissions,permission|Tool permissions|Разрешения инструментов|Ordered rules controlling actions on resources.|Упорядоченные правила доступа инструментов к ресурсам.
policies|Resource policies|Политики ресурсов|Allow or deny access to providers, tools and integrations.|Разрешение или запрет доступа к провайдерам, инструментам и интеграциям.
agents,agent|Agent definitions|Определения агентов|Named agents with instructions, models and permissions.|Именованные агенты с инструкциями, моделями и разрешениями.
snapshots,snapshot|File snapshots|Снимки файлов|Keep file snapshots for undo and revert.|Сохранение снимков файлов для отмены изменений.
watcher|File watching|Наблюдение за файлами|Control which filesystem changes OpenCode observes.|Управление отслеживанием изменений файловой системы.
ignore|Ignored paths|Исключённые пути|Patterns excluded from filesystem watching.|Шаблоны путей, изменения которых не отслеживаются.
formatter|Code formatting|Форматирование кода|Enable built-in formatters or override their commands.|Включение встроенных форматтеров или переопределение команд.
lsp|Language servers|Языковые серверы|Enable language services and configure custom LSP servers.|Включение языковых служб и настройка пользовательских LSP-серверов.
media,attachment|Attachments|Вложения|Processing options for files sent to models.|Параметры обработки файлов, отправляемых моделям.
image|Images|Изображения|Image resizing and payload limits.|Масштабирование и ограничения размера изображений.
auto_resize|Resize images|Уменьшать изображения|Resize images exceeding the configured limits.|Уменьшать изображения, превышающие заданные лимиты.
max_width|Maximum width|Максимальная ширина|Maximum image width in pixels.|Максимальная ширина изображения в пикселях.
max_height|Maximum height|Максимальная высота|Maximum image height in pixels.|Максимальная высота изображения в пикселях.
max_base64_bytes|Image payload size|Размер данных изображения|Maximum base64-encoded image size in bytes.|Максимальный размер изображения в кодировке base64, в байтах.
tool_output|Tool output limits|Лимиты вывода инструментов|Truncation thresholds for tool results.|Пороги обрезки результатов инструментов.
max_lines|Maximum lines|Максимум строк|Maximum tool output lines before truncation.|Максимальное число строк вывода до обрезки.
max_bytes|Maximum bytes|Максимум байтов|Maximum tool output bytes before truncation.|Максимальный объём вывода в байтах до обрезки.
mcp|MCP|MCP|Connections to external Model Context Protocol servers.|Подключения внешних серверов Model Context Protocol.
servers|Servers|Серверы|Named server connections; identifiers must be unique.|Именованные подключения к серверам; идентификаторы должны быть уникальными.
compaction|Context compaction|Сжатие контекста|How conversation history is summarized to fit the context window.|Как история разговора сокращается для размещения в контекстном окне.
auto|Automatic compaction|Автоматическое сжатие|Automatically compact when the context fills up.|Автоматически сжимать историю при заполнении контекста.
keep|Preserved context|Сохраняемый контекст|Amount of recent conversation retained without summarization.|Объём недавнего разговора, сохраняемый без пересказа.
tokens|Token count|Количество токенов|Token budget for this operation.|Бюджет токенов для этой операции.
buffer,reserved|Token reserve|Резерв токенов|Space reserved to avoid overflowing the context window.|Запас для предотвращения переполнения контекстного окна.
prune|Prune old outputs|Удалять старые результаты|Discard old tool outputs during compaction.|Удаление старых результатов инструментов при сжатии истории.
tail_turns|Recent turns|Последние ходы|How many recent user turns to preserve verbatim.|Число последних ходов пользователя, сохраняемых дословно.
preserve_recent_tokens|Preserved token budget|Бюджет сохраняемой истории|Maximum recent tokens preserved verbatim.|Максимум токенов недавней истории, сохраняемых дословно.
skills|Skills|Навыки|Additional directories or URLs for discovering skills.|Дополнительные каталоги и URL для поиска навыков.
instructions|Instruction sources|Источники инструкций|Files, patterns or URLs supplying additional instructions.|Файлы, шаблоны путей и URL с дополнительными инструкциями.
references,reference|Reference sources|Справочные источники|Named local directories or Git repositories for external context.|Именованные локальные каталоги или Git-репозитории с дополнительным контекстом.
commands,command|Commands|Команды|Named slash commands or process command with arguments.|Именованные слеш-команды либо команда запуска процесса с аргументами.
websearch|Web search|Веб-поиск|Provider used for internet searches.|Провайдер для поиска информации в интернете.
plugins,plugin|Plugins|Плагины|Plugin packages or local directories and their options.|Пакеты или локальные каталоги плагинов и их параметры.
worktree|Worktree defaults|Параметры рабочих деревьев|Default location for newly created Git worktrees.|Размещение новых рабочих деревьев Git.
warming|Session warming|Поддержание сессий|Send transient requests to keep recently used sessions warm.|Периодические служебные запросы для поддержания недавно использованных сессий.
providers,provider|Providers|Провайдеры|Provider definitions and model overrides; web search can choose a provider ID.|Определения провайдеров и моделей; для веб-поиска — идентификатор поискового провайдера.
experimental|Experimental options|Экспериментальные параметры|Features whose behavior can change between OpenCode releases.|Возможности, поведение которых может меняться между версиями OpenCode.
portable_shell_scanner|Portable command scanner|Переносимый анализатор команд|Alternative shell parser for permission checks.|Альтернативный разбор команд оболочки при проверке разрешений.
todo|Task tracking|Ведение списка задач|Expose the todowrite tool to agents.|Предоставить агентам инструмент todowrite для ведения списка задач.
background_compaction|Background compaction|Фоновое сжатие|Prepare conversation summaries ahead of time; background requests consume tokens.|Заранее готовить сводки разговора в фоне; фоновые запросы расходуют токены.
subagent_depth|Subagent depth|Глубина сабагентов|Maximum nesting depth; 1 allows children but not grandchildren.|Максимальная глубина вложенности; 1 разрешает дочерних агентов, но не их потомков.
location_idle_timeout|Workspace idle timeout|Выгрузка при простое|Duration such as 60 minutes, or false to keep idle workspace services loaded.|Время, например 60 minutes, либо false для сохранения служб неактивного пространства.
logLevel|Logging level|Уровень журналирования|Minimum severity written to logs at startup.|Минимальный уровень сообщений, записываемых в журнал при запуске.
server|Server startup|Запуск сервера|Listening address, port and network options for the server.|Адрес прослушивания, порт и сетевые параметры сервера.
hostname|Listen address|Адрес прослушивания|Host or network interface on which the server listens.|Хост или сетевой интерфейс, на котором сервер принимает соединения.
port,callback_port,callbackPort|Port|Порт|TCP port for this server or OAuth callback listener.|TCP-порт сервера или локального обработчика ответа OAuth.
mdns|Network discovery|Обнаружение в сети|Publish the service using mDNS.|Публикация сервиса для обнаружения через mDNS.
mdnsDomain|mDNS domain|Домен mDNS|Domain advertised for local service discovery.|Домен для обнаружения сервиса в локальной сети.
cors|Allowed origins|Разрешённые источники CORS|Additional origins allowed to access the server from a browser.|Дополнительные источники, которым разрешён доступ из браузера.
disabled_providers,blacklist|Disabled entries|Отключённые элементы|Provider or model IDs excluded from availability.|Идентификаторы провайдеров или моделей, исключённых из доступных.
enabled_providers,whitelist|Allowed entries|Разрешённые элементы|Only the listed provider or model IDs are enabled.|Доступны только перечисленные идентификаторы провайдеров или моделей.
mode|Agent mode|Режим агента|Whether an agent runs as primary, subagent, or both.|Запуск как основной агент, сабагент или в обоих режимах.
layout|Legacy layout|Старый режим компоновки|Deprecated layout option; current versions use stretch.|Устаревшая настройка; текущие версии используют растянутую компоновку.
tools|Tools|Инструменты|Tool availability or tool-calling capability for this model.|Доступность инструментов либо поддержка их вызова моделью.
action|Action|Действие|Tool action or policy action matched by this rule.|Действие инструмента или политики, к которому относится правило.
resource|Resource pattern|Шаблон ресурса|Path, command, URL or identifier pattern matched by the rule.|Шаблон пути, команды, URL или идентификатора для правила.
effect|Decision|Решение|Allow, deny or request approval for the matching action.|Разрешить, запретить или запросить подтверждение действия.
name,title|Display name|Отображаемое имя|Human-readable name shown in lists.|Название, отображаемое в списках.
id,providerID,modelID|Identifier|Идентификатор|Exact identifier used by the provider or OpenCode.|Точный идентификатор, используемый провайдером или OpenCode.
description|Description|Описание|Explains the purpose and when this entry should be used.|Описание назначения и условий использования.
system,prompt|Instructions|Инструкции|System instructions or text sent to the model.|Системные инструкции либо текст, отправляемый модели.
template|Command template|Шаблон команды|Prompt template used when the command is invoked.|Шаблон запроса при вызове команды.
temperature|Temperature|Температура|Sampling temperature controlling output variability.|Температура генерации, влияющая на разнообразие ответа.
top_p|Top-p sampling|Выборка top-p|Probability mass retained during token sampling.|Суммарная вероятность токенов, участвующих в выборке.
steps,maxSteps|Iteration limit|Лимит итераций|Maximum agent iterations before a text-only response.|Максимальное число итераций агента до текстового ответа.
hidden|Hide from menus|Скрыть из меню|Hide an agent from manual selection menus.|Скрыть агента из меню ручного выбора.
disable,disabled|Disabled|Отключено|Disable this model, agent, variant or service.|Отключить эту модель, агента, вариант или службу.
enabled|Enabled|Включено|Enable this connection when OpenCode initializes it.|Включать это подключение при его инициализации OpenCode.
color|Color|Цвет|Hexadecimal color or a supported theme color name.|Цвет в формате HEX или поддерживаемое название цвета темы.
variant,variants|Model variants|Варианты модели|Named model option presets such as reasoning effort.|Именованные наборы параметров модели, например глубины рассуждения.
subagent,subtask|Run as subagent|Выполнять как сабагент|Run the command in a separate child agent session.|Выполнять команду в отдельной дочерней сессии агента.
request,options,settings,initialization|Extra settings|Дополнительные параметры|Provider, plugin or service-specific configuration fields.|Параметры, специфичные для провайдера, плагина или службы.
package,npm|Package|Пакет|Package identifier used to load the integration.|Идентификатор пакета, из которого загружается интеграция.
url,baseURL,enterpriseUrl|Service URL|URL сервиса|Endpoint address used to connect to the service.|Адрес конечной точки для подключения к сервису.
apiKey|API key|Ключ API|API credential; an {env:NAME} reference avoids storing the secret here.|Ключ доступа к API; ссылка {env:NAME} позволяет не хранить секрет в этом файле.
headers|HTTP headers|Заголовки HTTP|Additional request headers; values may contain credentials.|Дополнительные заголовки запросов; значения могут содержать учётные данные.
env,environment|Environment variables|Переменные окружения|Variables passed to the spawned process.|Переменные, передаваемые запускаемому процессу.
cwd,directory,path,paths|Path or directory|Путь или каталог|Local file or directory path; relative paths follow the OpenCode configuration scope.|Локальный путь к файлу или каталогу; относительные пути зависят от области конфигурации OpenCode.
urls|Source URLs|URL источников|Web addresses used to discover external resources.|Веб-адреса для поиска внешних ресурсов.
repository|Git repository|Git-репозиторий|URL of the repository used as a reference.|URL репозитория, используемого как справочный источник.
branch|Git revision|Ветка или ревизия Git|Branch, tag or commit to use for the reference.|Ветка, тег или коммит справочного репозитория.
extensions|File extensions|Расширения файлов|File suffixes handled by this formatter or language server.|Расширения файлов, обрабатываемые форматтером или языковым сервером.
timeout,mcp_timeout|Request timeout|Тайм-аут запроса|Request timeout in milliseconds; false disables it where supported.|Тайм-аут запроса в миллисекундах; false отключает его там, где это поддерживается.
headerTimeout|Header timeout|Ожидание заголовков|Maximum time to wait for response headers, in milliseconds.|Максимальное ожидание заголовков ответа в миллисекундах.
chunkTimeout|Stream timeout|Ожидание потока|Maximum gap between streamed response chunks, in milliseconds.|Максимальная пауза между фрагментами потокового ответа в миллисекундах.
protocol,type|Connection type|Тип подключения|Protocol or discriminator selecting the connection format.|Протокол или признак, определяющий формат подключения.
oauth|OAuth configuration|Настройка OAuth|OAuth options for a remote MCP connection, or false to disable detection.|Параметры OAuth для удалённого MCP; false отключает автоматическое обнаружение.
client_id,clientId|OAuth client ID|Идентификатор клиента OAuth|Client identifier registered with the authorization server.|Идентификатор клиента, зарегистрированного на сервере авторизации.
client_secret,clientSecret|OAuth client secret|Секрет клиента OAuth|Client secret required by the authorization server.|Секрет клиента, требуемый сервером авторизации.
redirect_uri,redirectUri|OAuth callback URL|URL возврата OAuth|URL receiving the authorization response.|URL, на который поступает ответ авторизации.
scope|OAuth scopes|Области доступа OAuth|Permission scopes requested during authorization.|Области доступа, запрашиваемые при авторизации.
auth_server_metadata_url|Authorization metadata|Метаданные авторизации|URL for discovering authorization server metadata.|URL для получения метаданных сервера авторизации.
models|Model definitions|Определения моделей|Named model definitions and capability overrides.|Именованные определения моделей и переопределения их возможностей.
capabilities|Model capabilities|Возможности модели|Supported inputs, outputs, reasoning and tool use.|Поддерживаемые входные данные, ответы, рассуждения и инструменты.
limit|Model limits|Лимиты модели|Context, input and output token limits.|Ограничения токенов контекста, входа и ответа.
context|Context window|Контекстное окно|Maximum context size in tokens.|Максимальный размер контекста в токенах.
input,output|Input / output|Вход / выход|Input or output limit, capability or price depending on the parent section.|Лимит, формат или стоимость входа/выхода в зависимости от раздела.
cost|Model pricing|Стоимость модели|Token prices used for cost estimates.|Цены токенов для оценки стоимости запросов.
cache,cache_read,cache_write|Prompt cache|Кэш запросов|Cache settings or prices for cache reads and writes.|Параметры кэша либо стоимость чтения и записи кэша запросов.
reasoning|Reasoning|Рассуждения|Reasoning support and model-specific controls.|Поддержка рассуждений и параметры, специфичные для модели.
effort|Reasoning effort|Глубина рассуждения|Model reasoning effort value supported by its provider.|Поддерживаемое провайдером значение глубины рассуждения модели.
budget|Reasoning budget|Бюджет рассуждения|Token budget allocated to reasoning.|Бюджет токенов, выделенных на рассуждения.
family|Model family|Семейство модели|Family identifier used for grouping model releases.|Идентификатор семейства для группировки выпусков моделей.
release_date,releaseDate|Release date|Дата выпуска|Model release date in year-month-day or supported year-month form.|Дата выпуска модели: год-месяц-день либо поддерживаемый формат год-месяц.
status|Model status|Статус модели|Availability stage such as alpha, beta or deprecated.|Стадия доступности: альфа, бета, устаревшая и другие поддерживаемые значения.
modalities|Supported formats|Поддерживаемые форматы|Input and output content types supported by the model.|Типы входного и выходного содержимого, поддерживаемые моделью.
tool_call|Tool calling|Вызов инструментов|Whether the model supports invoking tools.|Поддерживает ли модель вызов инструментов.
transport|API transport|Транспорт API|Protocol used for model requests, such as HTTP or WebSocket.|Протокол запросов к модели, например HTTP или WebSocket.
encoding|Payload encoding|Кодирование данных|Compression or encoding used for request payloads.|Сжатие или кодирование данных запроса.
compatibility|Compatibility mode|Режим совместимости|Provider-specific adaptations of the request and response formats.|Адаптация форматов запросов и ответов к особенностям провайдера.
duration|Active duration|Продолжительность|Duration string, for example 30 minutes.|Строка длительности, например 30 minutes.
interval|Request interval|Интервал запросов|Duration between periodic requests, for example 4 minutes.|Пауза между периодическими запросами, например 4 minutes.
startup|Startup behavior|Поведение при запуске|Integration startup options.|Параметры запуска интеграции.
execution|Execution options|Параметры выполнения|Controls how this command or integration executes.|Управляет выполнением команды или интеграции.
body|Request body|Тело запроса|Additional JSON properties in the API request body.|Дополнительные поля JSON в теле запроса API.
catalog|Model catalog|Каталог моделей|Model catalog source or catalog overrides.|Источник каталога моделей или его переопределения.
api|API mapping|Сопоставление API|Provider API identifiers for this model.|Идентификаторы модели в API провайдера.
supported|Supported values|Поддерживаемые значения|Values accepted by this model feature.|Значения, допустимые для данной возможности модели.
min,max|Value bound|Граница значения|Minimum or maximum supported value.|Минимальное или максимальное поддерживаемое значение.
field,reasoningField|API field|Поле API|Name of the provider-specific API field.|Имя поля API, специфичного для провайдера.
maxTokensField|Output token field|Поле лимита ответа|API field used to specify the output token limit.|Поле API для указания максимального количества токенов ответа.
cacheFormat|Cache format|Формат кэша|Provider-specific prompt caching format.|Формат кэширования запросов, специфичный для провайдера.
tier|Pricing tier|Тарифный уровень|Price tier and the condition selecting it.|Тарифный уровень и условие его применения.
size,context_over_200k|Tier size|Порог тарифа|Context size selecting a different pricing tier.|Размер контекста, при котором применяется другой тариф.
interleaved|Interleaved reasoning|Чередование рассуждений|How reasoning blocks are interleaved with other output.|Как блоки рассуждений чередуются с остальным ответом.
setCacheKey,supportsPromptCacheKey|Prompt cache key|Ключ кэша запроса|Support for a provider prompt-cache key.|Поддержка ключа кэша запросов провайдера.
streamUsage|Stream token usage|Расход токенов в потоке|Include token usage statistics in streaming responses.|Передача статистики токенов в потоковом ответе.
requireFinishReason|Require finish reason|Требовать причину завершения|Compatibility requirement for response finish reasons.|Требование совместимости к причине завершения ответа.
requireReasoning|Require reasoning|Требовать рассуждения|Compatibility requirement for reasoning content.|Требование совместимости к содержимому рассуждений.
requireAssistantAfterTool|Assistant after tool|Ответ после инструмента|Require an assistant message after tool output.|Требовать сообщение ассистента после результата инструмента.
supportsEffortUpdates|Effort updates|Изменение глубины|Whether reasoning effort can be updated in the session.|Можно ли менять глубину рассуждения в рамках сессии.
supportsThinkingBlockBinding|Thinking block binding|Связь блоков рассуждения|Provider support for binding thinking blocks.|Поддержка связывания блоков рассуждения провайдером.
canonical|Canonical reference|Основная ссылка|Canonical identifier for this configuration entry.|Основной идентификатор этой записи конфигурации.
codemode|Code execution mode|Режим выполнения кода|Code execution support for this integration.|Поддержка выполнения кода в интеграции.
disable_paste_summary|Disable paste summary|Отключить сводку вставки|Legacy option controlling pasted-content summaries.|Старый параметр управления сводками вставленного содержимого.
batch_tool|Batch tool|Пакетный инструмент|Expose the legacy batch execution tool.|Предоставить старый инструмент пакетного выполнения.
openTelemetry|OpenTelemetry|OpenTelemetry|Emit telemetry spans for AI SDK requests.|Создание записей трассировки для запросов AI SDK.
primary_tools|Primary-only tools|Инструменты основного агента|Tools restricted to primary agents.|Инструменты, доступные только основным агентам.
continue_loop_on_deny|Continue after denial|Продолжать после запрета|Continue the agent loop after a tool request is denied.|Продолжать работу агента после запрета вызова инструмента.
topP|Nucleus sampling (top P)|Ядерная выборка (top P)|Keep the smallest set of tokens whose probabilities add up to this value.|Оставлять минимальный набор токенов, чьи вероятности дают эту сумму.
topK|Top-K sampling|Отбор top K|Only the K most likely tokens are considered at each step.|На каждом шаге рассматриваются только K самых вероятных токенов.
minP|Minimum probability (min P)|Минимальная вероятность (min P)|Drop tokens whose probability falls below this share of the most likely candidate.|Отбрасывать токены, чья вероятность ниже этой доли от самого вероятного.
reasoningEffort|Reasoning effort|Глубина рассуждения|How much reasoning the model is asked for, where it reasons and its provider names the levels.|Сколько рассуждений запросить у модели, если она рассуждает и провайдер различает уровни.
presencePenalty|Presence penalty|Штраф за присутствие|Subtract from the score of tokens that already appeared in the text.|Вычитать из веса токенов, которые уже встречались в тексте.
frequencyPenalty|Frequency penalty|Штраф за частоту|Subtract from the score of tokens in proportion to how often they appeared.|Вычитать из веса токенов пропорционально тому, как часто они встречались.
maxOutputTokens|Maximum output tokens|Максимум токенов ответа|Largest number of tokens a single answer may produce.|Наибольшее число токенов, которое может выдать один ответ.
seed|Random seed|Зерно генератора|A fixed seed makes the answer reproducible where the server supports it.|Фиксированное зерно делает ответ воспроизводимым, если сервер это поддерживает.
stopSequences|Stop sequences|Останавливающие последовательности|Generation stops as soon as one of these strings appears.|Генерация прекращается, как только появляется одна из этих строк.
"""
FIELDS = {}
for _line in _FIELDS.strip().splitlines():
    _keys, *_values = _line.split("|")
    for _key in _keys.split(","):
        FIELDS[_key] = tuple(_values)

ENUMS = {
    "allow": "Разрешить", "deny": "Запретить", "ask": "Запрашивать", "auto": "Автоматически",
    "notify": "Уведомлять", "disable": "Отключить", "disabled": "Отключено", "manual": "Вручную",
    "primary": "Основной", "subagent": "Сабагент", "all": "Оба режима", "random": "Случайный",
    "local": "Локальный", "remote": "Удалённый", "native": "Нативный", "summary": "Сводка",
    "none": "Нет", "text": "Текст", "image": "Изображение", "audio": "Аудио", "video": "Видео",
    "active": "Активная", "deprecated": "Устаревшая", "alpha": "Альфа", "beta": "Бета",
    "provider.use": "Доступ к провайдеру", "tool.use": "Доступ к инструменту", "integration.use": "Доступ к интеграции",
    "DEBUG": "Отладка", "INFO": "Информация", "WARN": "Предупреждения", "ERROR": "Ошибки",
}


def t(key: str, **values) -> str:
    result = UI[key][language() == "ru"]
    return result.format(**values) if values else result


def field_entry(path: tuple):
    key = str(path[-1])
    if path[0] == "mcp" and len(path) >= 2 and path[-2] == "timeout":
        return {
            "startup": ("Startup timeout (ms)", "Тайм-аут запуска (мс)", "Maximum time to start and initialize a server, in milliseconds.", "Максимальное время запуска и инициализации сервера в миллисекундах."),
            "catalog": ("Catalog timeout (ms)", "Тайм-аут каталога (мс)", "Maximum time to list server tools and resources, in milliseconds.", "Максимальное время получения списка инструментов и ресурсов сервера в миллисекундах."),
            "execution": ("Execution timeout (ms)", "Тайм-аут выполнения (мс)", "Maximum time for an MCP tool call, in milliseconds.", "Максимальное время вызова инструмента MCP в миллисекундах."),
        }.get(key, FIELDS.get(key))
    if path[0] == "mcp" and len(path) == 3 and path[1] == "servers":
        return (key, key, "Configure this MCP server connection. Choose local for a process or remote for an HTTP endpoint.",
                "Подключение сервера MCP. Выберите локальный тип для запуска процесса или удалённый для HTTP-адреса.")
    entry = FIELDS.get(key)
    if entry is None and len(path) > 1:
        parent = FIELDS.get(str(path[-2]))
        if parent: return (key, key, parent[2], parent[3])
    return entry


def field_name(path: tuple, info=None) -> str:
    entry = field_entry(path)
    return entry[language() == "ru"] if entry else str(path[-1])


def field_help(path: tuple, info: dict) -> str:
    key = str(path[-1])
    entry = field_entry(path)
    if language() == "ru":
        result = entry[3] if entry else t("customHint")
    else:
        result = info.get("description") or (entry[2] if entry else t("customHint"))
    return f"{result}\n\n{'.'.join(str(x) for x in path)}\n{t('inheritHint')}"


def enum_label(value) -> str:
    if value is True: return t("on")
    if value is False: return t("off")
    if value is None: return t("null")
    if language() == "ru" and value in ENUMS:
        return f"{ENUMS[value]} ({value})"
    return str(value)
