from tools.quick_tools import _attr_text


class FakeTag:
    def __init__(self, value):
        self.value = value

    def get(self, name, default=""):
        return self.value if name == "content" else default


class TestAttrText:
    def test_none_tag_returns_default(self):
        assert _attr_text(None, "content") == ""

    def test_none_attribute_returns_default(self):
        assert _attr_text(FakeTag(None), "content") == ""

    def test_list_attribute_is_joined(self):
        assert _attr_text(FakeTag(["one", "two"]), "content") == "one two"

    def test_string_attribute_is_stripped(self):
        assert _attr_text(FakeTag("  hello  "), "content") == "hello"
