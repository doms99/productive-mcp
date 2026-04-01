# Productive Task MCP

Local Python package that runs both as:

- a `stdio` MCP server for Cursor tools
- a companion CLI for manual/scripting workflows

## Features

- Task tools: list tasks, fetch a task by `task_number` or `id`, find tasks by status and/or custom fields
- Comment tools: list comments by task, add task comments, update comments
- Optional comment context in `productive_get_task`
- Lookup tools: projects, task lists, workflow statuses, custom fields, people
- Shared config/client/query logic between MCP and CLI

## Requirements

- Python 3.11+

## Install

From repo root:

```bash
python3 -m pip install -e .
```

Install directly from GitHub:

```bash
python3 -m pip install "git+https://github.com/doms99/productive-mcp.git@main"
```

Install via `curl` + script:

```bash
curl -fsSL "https://raw.githubusercontent.com/doms99/productive-mcp/main/install.sh" | bash
```

## Config

`PRODUCTIVE_API_TOKEN` is resolved in this order:

1. `productive-mcp-server --api-token ...`
2. `PRODUCTIVE_API_TOKEN` environment variable

Other settings (`PRODUCTIVE_ORGANIZATION_ID`, `PRODUCTIVE_PROJECT_ID`, `PRODUCTIVE_BASE_URL`) are resolved in this order:

1. server arguments (`--organization-id`, `--project-id`, `--base-url`, `--config-path`)
2. environment variables
3. `.productive-mcp.json`

Create a config file named `.productive-mcp.json` in:

- your current working directory (preferred), or
- your home directory

Example:

```json
{
  "PRODUCTIVE_ORGANIZATION_ID": "your-org-id",
  "PRODUCTIVE_PROJECT_ID": "your-default-project-id",
  "PRODUCTIVE_BASE_URL": "https://api.productive.io"
}
```

`PRODUCTIVE_API_TOKEN` must be passed via `--api-token` or the `PRODUCTIVE_API_TOKEN` environment variable.
`PRODUCTIVE_BASE_URL` is optional and defaults to `https://api.productive.io`.
`PRODUCTIVE_PROJECT_ID` is optional and is used as a default `project_id` filter for task listing in both MCP and CLI.
If you pass `project_id` explicitly in task filters, that explicit value takes precedence.

## Cursor MCP Registration

Add this server definition to your Cursor MCP config:

```json
{
  "mcpServers": {
    "productive-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/doms99/productive-mcp.git@main",
        "productive-mcp-server",
        "--api-token",
        "your-token",
        "--organization-id",
        "your-org-id"
      ]
    }
  }
}
```

If you do not pass `--api-token`, the server falls back to `PRODUCTIVE_API_TOKEN` from the environment.

If needed, install from GitHub first, then use the installed entrypoint:

```json
{
  "mcpServers": {
    "productive-mcp": {
      "command": "productive-mcp-server"
    }
  }
}
```

## MCP Tools

### `productive_test_connection`

Validate that your Productive credentials are configured correctly.


| Parameter     | Type   | Default                  | Description         |
| ------------- | ------ | ------------------------ | ------------------- |
| `config_path` | string | `./.productive-mcp.json` | Path to config file |


### `productive_list_tasks`

List tasks with full filter, sort, pagination, include, and sparse fieldset support.


| Parameter     | Type   | Default                  | Description                                                   |
| ------------- | ------ | ------------------------ | ------------------------------------------------------------- |
| `filters`     | object | —                        | Filter params (e.g. `{"project_id": "123", "status": "1"}`)   |
| `filter_ops`  | object | —                        | Operator filters (e.g. `{"due_date": {"lt": "2025-01-01"}}`)  |
| `sort`        | string | —                        | Sort field (e.g. `"-created_at"` for descending)              |
| `page_number` | int    | —                        | Page number                                                   |
| `page_size`   | int    | —                        | Results per page                                              |
| `include`     | string | —                        | Comma-separated related resources (e.g. `"project,assignee"`) |
| `fields`      | object | —                        | Sparse fieldsets (e.g. `{"tasks": ["name", "status"]}`)       |
| `config_path` | string | `./.productive-mcp.json` | Path to config file                                           |


### `productive_get_task`

Fetch a single task by task number (default) or by ID, with optional comments.


| Parameter            | Type   | Default                  | Description                               |
| -------------------- | ------ | ------------------------ | ----------------------------------------- |
| `task_reference`     | string | **required**             | Task number or ID                         |
| `lookup_by`          | string | `"task_number"`          | `"task_number"` or `"id"`                 |
| `include`            | string | —                        | Comma-separated related resources         |
| `fields`             | object | —                        | Sparse fieldsets                          |
| `include_comments`   | bool   | `false`                  | Fetch and attach comments to the response |
| `comments_page_size` | int    | `50`                     | Number of comments to fetch               |
| `config_path`        | string | `./.productive-mcp.json` | Path to config file                       |


### `productive_list_custom_fields`

List all task custom fields for the configured project, including available options for select/multi-select fields.


| Parameter     | Type   | Default                  | Description         |
| ------------- | ------ | ------------------------ | ------------------- |
| `config_path` | string | `./.productive-mcp.json` | Path to config file |


Returns each field's `id`, `name`, `data_type_id` (1=text, 2=number, 3=select, 4=date, 5=multi-select, 6=person, 7=attachment), and `options` for select fields.

### `productive_find_tasks`

Find tasks by workflow status name and/or custom field values. Resolves human-friendly names to IDs automatically.


| Parameter              | Type   | Default                  | Description                                                     |
| ---------------------- | ------ | ------------------------ | --------------------------------------------------------------- |
| `status_name`          | string | —                        | Workflow status name (e.g. `"In Progress"`, case-insensitive)   |
| `custom_field_filters` | object | —                        | Custom field name → value pairs (e.g. `{"Sprint": "Sprint 4"}`) |
| `project_id`           | string | —                        | Filter to a specific project                                    |
| `page_number`          | int    | —                        | Page number                                                     |
| `page_size`            | int    | `50`                     | Results per page                                                |
| `include`              | string | —                        | Comma-separated related resources                               |
| `fields`               | object | —                        | Sparse fieldsets                                                |
| `config_path`          | string | `./.productive-mcp.json` | Path to config file                                             |


**Examples:**

```
# All "In Progress" tasks
productive_find_tasks(status_name="In Progress")

# All tasks in Sprint 4
productive_find_tasks(custom_field_filters={"Sprint": "Sprint 4"})

# "In Progress" tasks on Flutter platform in Sprint 4
productive_find_tasks(
    status_name="In Progress",
    custom_field_filters={"Sprint": "Sprint 4", "Platform": "Flutter"}
)
```

### `productive_list_task_comments`

List comments for a task.


| Parameter     | Type   | Default                  | Description                       |
| ------------- | ------ | ------------------------ | --------------------------------- |
| `task_id`     | string | **required**             | Task ID                           |
| `sort`        | string | `"created_at"`           | Sort field                        |
| `page_number` | int    | —                        | Page number                       |
| `page_size`   | int    | —                        | Results per page                  |
| `include`     | string | `"person"`               | Comma-separated related resources |
| `config_path` | string | `./.productive-mcp.json` | Path to config file               |



### `productive_list_projects`

List projects (compact format: id, name, code, state).


| Parameter     | Type   | Default                  | Description         |
| ------------- | ------ | ------------------------ | ------------------- |
| `filters`     | object | —                        | Filter params       |
| `sort`        | string | —                        | Sort field          |
| `page_number` | int    | —                        | Page number         |
| `page_size`   | int    | `50`                     | Results per page    |
| `config_path` | string | `./.productive-mcp.json` | Path to config file |


### `productive_list_task_lists`

List task lists (compact format: id, name, code, state).


| Parameter     | Type   | Default                  | Description         |
| ------------- | ------ | ------------------------ | ------------------- |
| `filters`     | object | —                        | Filter params       |
| `sort`        | string | —                        | Sort field          |
| `page_number` | int    | —                        | Page number         |
| `page_size`   | int    | `50`                     | Results per page    |
| `config_path` | string | `./.productive-mcp.json` | Path to config file |


### `productive_list_workflow_statuses`

List workflow statuses (compact format: id, name, state).


| Parameter     | Type   | Default                  | Description         |
| ------------- | ------ | ------------------------ | ------------------- |
| `filters`     | object | —                        | Filter params       |
| `sort`        | string | —                        | Sort field          |
| `page_number` | int    | —                        | Page number         |
| `page_size`   | int    | `50`                     | Results per page    |
| `config_path` | string | `./.productive-mcp.json` | Path to config file |


### `productive_list_people`

List people (compact format: id, name, email).


| Parameter     | Type   | Default                  | Description         |
| ------------- | ------ | ------------------------ | ------------------- |
| `filters`     | object | —                        | Filter params       |
| `sort`        | string | —                        | Sort field          |
| `page_number` | int    | —                        | Page number         |
| `page_size`   | int    | `50`                     | Results per page    |
| `config_path` | string | `./.productive-mcp.json` | Path to config file |


## CLI Usage

General help:

```bash
productive-mcp --help
```

All commands support `--config-path` to point to a specific config file and `--raw` for raw JSON output.

### `test-connection`

```bash
productive-mcp test-connection [--config-path PATH] [--raw]
```

### `list-tasks`

```bash
productive-mcp list-tasks [OPTIONS]
```


| Option          | Description                                            | Example                                     |
| --------------- | ------------------------------------------------------ | ------------------------------------------- |
| `--filter`      | Repeatable `key=value` filter (see filter keys below)  | `--filter project_id=123 --filter status=1` |
| `--filter-op`   | Repeatable `field:operator:value` filter               | `--filter-op completed_at:not_exists:true`  |
| `--include`     | Repeatable relationship to include                     | `--include project --include assignee`      |
| `--field`       | Repeatable sparse fieldset as `resource:field1,field2` | `--field tasks:name,status`                 |
| `--sort`        | Sort expression (prefix with `-` for descending)       | `--sort -created_at`                        |
| `--page-number` | Page number                                            | `--page-number 2`                           |
| `--page-size`   | Results per page                                       | `--page-size 10`                            |


**Available filter keys:**


| Key                           | Values / Type                                    |
| ----------------------------- | ------------------------------------------------ |
| `status`                      | `1` = open, `2` = closed                         |
| `project_id`                  | ID (array)                                       |
| `task_list_id`                | finID (array)                                    |
| `assignee_id`                 | ID (array)                                       |
| `workflow_status_id`          | ID (array)                                       |
| `workflow_id`                 | ID (array)                                       |
| `workflow_status_category_id` | `1` = not started, `2` = started, `3` = closed   |
| `board_id`                    | ID (array)                                       |
| `board_status`                | `1` = active, `2` = archived                     |
| `company_id`                  | ID (array)                                       |
| `creator_id`                  | ID (array)                                       |
| `subscriber_id`               | ID (array)                                       |
| `parent_task_id`              | ID (array)                                       |
| `project_manager_id`          | ID (array)                                       |
| `last_actor_id`               | ID                                               |
| `task_number`                 | string                                           |
| `title`                       | string                                           |
| `query`                       | free-text search                                 |
| `description`                 | string                                           |
| `tags`                        | string                                           |
| `task_type`                   | `1` = parent task, `2` = subtask                 |
| `task_list_status`            | `1` = open, `2` = closed                         |
| `task_list_name`              | string                                           |
| `board_name`                  | string                                           |
| `due_date`                    | `1` = any, `2` = overdue                         |
| `due_date_on`                 | date string                                      |
| `due_date_after`              | date string                                      |
| `due_date_before`             | date string                                      |
| `start_date`                  | date string                                      |
| `start_date_after`            | date string                                      |
| `start_date_before`           | date string                                      |
| `created_at`                  | date string                                      |
| `updated_at`                  | date string                                      |
| `closed_at`                   | date string                                      |
| `closed_after`                | date string                                      |
| `closed_before`               | date string                                      |
| `last_activity`               | date string                                      |
| `last_activity_after`         | date string                                      |
| `last_activity_before`        | date string                                      |
| `after`                       | date string                                      |
| `before`                      | date string                                      |
| `date_range`                  | date range                                       |
| `overdue_status`              | `1` = not overdue, `2` = overdue                 |
| `person_type`                 | `1` = user, `2` = contact, `3` = placeholder     |
| `project_type`                | `1` = internal project, `2` = client project     |
| `public_access`               | boolean                                          |
| `repeating`                   | boolean                                          |
| `dependency_type`             | string                                           |
| `billable_time`               | number                                           |
| `worked_time`                 | number                                           |
| `remaining_time`              | number                                           |
| `initial_estimate`            | number                                           |
| `custom_fields`               | nested (use `find-tasks --cf` for easier access) |


### `find-tasks`

```bash
productive-mcp find-tasks [OPTIONS]
```


| Option          | Description                                            | Example                                          |
| --------------- | ------------------------------------------------------ | ------------------------------------------------ |
| `--status`      | Workflow status name (case-insensitive)                | `--status "In Progress"`                         |
| `--cf`          | Repeatable custom field filter as `Name=Value`         | `--cf "Sprint=Sprint 4" --cf "Platform=Flutter"` |
| `--include`     | Repeatable relationship to include                     | `--include project`                              |
| `--field`       | Repeatable sparse fieldset as `resource:field1,field2` | `--field tasks:name,status`                      |
| `--page-number` | Page number                                            | `--page-number 2`                                |
| `--page-size`   | Results per page (default: 50)                         | `--page-size 10`                                 |


Use `list-workflow-statuses` to see available `--status` values. Use `list-custom-fields` to see available `--cf` field names and their options.

**Examples:**

```bash
productive-mcp find-tasks --status "In Progress"
productive-mcp find-tasks --cf "Sprint=Sprint 4"
productive-mcp find-tasks --status "In Progress" --cf "Sprint=Sprint 4" --cf "Platform=Flutter"
```

### `get-task`

```bash
productive-mcp get-task TASK_REFERENCE [OPTIONS]
```


| Option                 | Description                                  | Example                    |
| ---------------------- | -------------------------------------------- | -------------------------- |
| `TASK_REFERENCE`       | Task number (default) or task ID             | `987`                      |
| `--by-id`              | Treat reference as task ID instead of number | `--by-id`                  |
| `--include`            | Repeatable relationship to include           | `--include project`        |
| `--field`              | Repeatable sparse fieldset                   | `--field tasks:name`       |
| `--include-comments`   | Also fetch task comments                     | `--include-comments`       |
| `--comments-page-size` | Comments page size (default: 50)             | `--comments-page-size 100` |


### `list-task-comments`

```bash
productive-mcp list-task-comments TASK_ID [OPTIONS]
```


| Option          | Description                                 | Example              |
| --------------- | ------------------------------------------- | -------------------- |
| `TASK_ID`       | Task ID (required)                          | `12345`              |
| `--sort`        | Sort expression (default: `created_at`)     | `--sort -created_at` |
| `--include`     | Repeatable relationship (default: `person`) | `--include person`   |
| `--page-number` | Page number                                 | `--page-number 2`    |
| `--page-size`   | Results per page                            | `--page-size 10`     |



### `list-projects`

```bash
productive-mcp list-projects [OPTIONS]
```


| Option          | Description                    | Example             |
| --------------- | ------------------------------ | ------------------- |
| `--filter`      | Repeatable `key=value` filter  | `--filter status=1` |
| `--sort`        | Sort expression                | `--sort name`       |
| `--page-number` | Page number                    | `--page-number 2`   |
| `--page-size`   | Results per page (default: 50) | `--page-size 10`    |


**Available filter keys:**


| Key              | Values / Type                |
| ---------------- | ---------------------------- |
| `id`             | ID                           |
| `status`         | `1` = active, `2` = archived |
| `project_type`   | `1` = internal, `2` = client |
| `company_id`     | ID (array)                   |
| `responsible_id` | ID (array)                   |
| `person_id`      | ID (array)                   |
| `query`          | free-text search             |


### `list-task-lists`

```bash
productive-mcp list-task-lists [OPTIONS]
```


| Option          | Description                    | Example             |
| --------------- | ------------------------------ | ------------------- |
| `--filter`      | Repeatable `key=value` filter  | `--filter status=1` |
| `--sort`        | Sort expression                | `--sort name`       |
| `--page-number` | Page number                    | `--page-number 2`   |
| `--page-size`   | Results per page (default: 50) | `--page-size 10`    |


**Available filter keys:**


| Key          | Values / Type                |
| ------------ | ---------------------------- |
| `id`         | ID                           |
| `project_id` | ID (array)                   |
| `board_id`   | ID (array)                   |
| `status`     | `1` = active, `2` = archived |


### `list-workflow-statuses`

```bash
productive-mcp list-workflow-statuses [OPTIONS]
```


| Option          | Description                    | Example                  |
| --------------- | ------------------------------ | ------------------------ |
| `--filter`      | Repeatable `key=value` filter  | `--filter category_id=2` |
| `--sort`        | Sort expression                | `--sort name`            |
| `--page-number` | Page number                    | `--page-number 2`        |
| `--page-size`   | Results per page (default: 50) | `--page-size 10`         |


**Available filter keys:**


| Key           | Values / Type                                  |
| ------------- | ---------------------------------------------- |
| `name`        | string                                         |
| `workflow_id` | ID                                             |
| `category_id` | `1` = not started, `2` = started, `3` = closed |


### `list-custom-fields`

```bash
productive-mcp list-custom-fields [--config-path PATH] [--raw]
```

Lists all task custom fields for the configured project with their available options (for select/multi-select fields). No additional filters — fetches everything automatically.

### `list-people`

```bash
productive-mcp list-people [OPTIONS]
```


| Option          | Description                    | Example             |
| --------------- | ------------------------------ | ------------------- |
| `--filter`      | Repeatable `key=value` filter  | `--filter status=1` |
| `--sort`        | Sort expression                | `--sort name`       |
| `--page-number` | Page number                    | `--page-number 2`   |
| `--page-size`   | Results per page (default: 50) | `--page-size 10`    |


**Available filter keys:**


| Key                             | Values / Type                                          |
| ------------------------------- | ------------------------------------------------------ |
| `id`                            | ID                                                     |
| `email`                         | string                                                 |
| `status`                        | `1` = active, `2` = deactivated                        |
| `person_type`                   | `1` = user, `2` = contact, `3` = placeholder           |
| `role_id`                       | ID (array)                                             |
| `company_id`                    | ID (array)                                             |
| `project_id`                    | ID                                                     |
| `manager_id`                    | ID                                                     |
| `custom_role_id`                | ID                                                     |
| `tags`                          | string                                                 |
| `query`                         | free-text search                                       |
| `team`                          | string                                                 |
| `subscribable_type`             | `task`, `deal`, `person`, `company`, `invoice`, `page` |
| `subscribable_id`               | ID (array)                                             |
| `last_activity_at`              | date string                                            |
| `two_factor_auth`               | boolean                                                |
| `autotracking`                  | boolean                                                |
| `timesheet_submission_disabled` | boolean                                                |
| `time_tracking_policy_id`       | ID                                                     |
| `service_type_id`               | ID                                                     |


## Development Smoke Checks

From repo root:

```bash
python3 -m pip install -e .
python3 -m productive_mcp.cli --help
python3 -c "import productive_mcp.server as s; print(s.mcp.name)"
```

Optional live validation (requires credentials):

```bash
productive-mcp test-connection
productive-mcp list-tasks --page-size 5
```

