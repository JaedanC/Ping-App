import pygui

class EditableString:
    def __init__(self, content: pygui.String, _id: int):
        self._content = content
        self._id = _id
        self._is_editting = False

    def draw(self):
        pygui.push_id(self._id)
        if pygui.small_button("/###Rename button"):
            pygui.set_keyboard_focus_here()
            self._is_editting = True
        pygui.same_line()
        
        self._did_save = False
        if self._is_editting:
            if pygui.is_key_pressed(pygui.KEY_ESCAPE):
                self._is_editting = False

            if pygui.input_text("###Renaming file", self._content, pygui.INPUT_TEXT_FLAGS_ENTER_RETURNS_TRUE):
                self._did_save = True
                self._is_editting = False
        else:
            pygui.text(self._content.value)
        pygui.pop_id()

    def is_editting(self) -> bool:
        return self._is_editting
    
    def did_save(self) -> bool:
        return self._did_save

    def content(self) -> pygui.String:
        return self._content
