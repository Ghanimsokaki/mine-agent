from src.browser_actions import extract_browser_actions


def test_extracts_safe_actions():
    response = '''I can queue this.
```browser-actions
[{"action":"insert_code","selector":"textarea.editor","text":"print('hi')","description":"Insert a greeting"}]
```
'''
    actions = extract_browser_actions(response)
    assert actions == [{"action": "insert_code", "description": "Insert a greeting", "selector": "textarea.editor", "text": "print('hi')"}]


def test_blocks_password_actions():
    response = '''```browser-actions
[{"action":"type","selector":"input[type=password]","text":"nope","description":"enter password"}]
```'''
    assert extract_browser_actions(response) == []
