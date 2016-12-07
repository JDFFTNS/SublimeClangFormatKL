import sublime, sublime_plugin
import subprocess, os
import re, string, random, time

from collections import namedtuple

# The styles available by default. We add one option: "Custom". This tells
# the plugin to look in an ST settings file to load the customised style.
styles  = ["LLVM", "Google", "Chromium", "Mozilla", "WebKit", "Custom", "File"]


# Settings file locations.
settings_file = 'clang_format.sublime-settings'
custom_style_settings = 'clang_format_custom.sublime-settings'


# Hacky, but there doesn't seem to be a cleaner way to do this for now.
# We need to be able to load all these settings from the settings file.
all_settings  = [
    "BasedOnStyle", "AccessModifierOffset", "AlignAfterOpenBracket",
    "AlignConsecutiveAssignments", "AlignConsecutiveDeclarations",
    "AlignEscapedNewlinesLeft", "AlignOperands", "AlignTrailingComments",
    "AllowAllParametersOfDeclarationOnNextLine",
    "AllowShortBlocksOnASingleLine", "AllowShortCaseLabelsOnASingleLine",
    "AllowShortFunctionsOnASingleLine", "AllowShortIfStatementsOnASingleLine",
    "AllowShortLoopsOnASingleLine", "AlwaysBreakAfterDefinitionReturnType",
    "AlwaysBreakBeforeMultilineStrings", "AlwaysBreakTemplateDeclarations",
    "BinPackArguments", "BinPackParameters", "BraceWrapping",
    "BreakAfterJavaFieldAnnotations", "BreakBeforeBinaryOperators", 
    "BreakBeforeBraces", "BreakBeforeTernaryOperators", 
    "BreakConstructorInitializersBeforeComma", "ColumnLimit", "CommentPragmas",
    "ConstructorInitializerAllOnOneLineOrOnePerLine",
    "ConstructorInitializerIndentWidth", "ContinuationIndentWidth",
    "Cpp11BracedListStyle", "DerivePointerAlignment", "DisableFormat",
    "ExperimentalAutoDetectBinPacking", "ForEachMacros", "IncludeCategories", 
    "IndentCaseLabels", "IndentWidth", "IndentWrappedFunctionNames",
    "KeepEmptyLinesAtTheStartOfBlocks", "Language", "MacroBlockBegin", "MacroBlockEnd",
    "MaxEmptyLinesToKeep", "NamespaceIndentation", "ObjCBlockIndentWidth",
    "ObjCSpaceAfterProperty", "ObjCSpaceBeforeProtocolList",
    "PenaltyBreakBeforeFirstCallParameter", "PenaltyBreakComment",
    "PenaltyBreakFirstLessLess", "PenaltyBreakString", "BreakStringLiterals",
    "PenaltyExcessCharacter", "PenaltyReturnTypeOnItsOwnLine", "PointerAlignment",
    "SpaceAfterCStyleCast", "SpaceBeforeAssignmentOperators", "SpaceBeforeParens",
    "SpaceInEmptyParentheses", "SpacesBeforeTrailingComments", "SpacesInAngles",
    "SpacesInCStyleCastParentheses", "SpacesInContainerLiterals",
    "SpacesInParentheses", "SpacesInSquareBrackets", "Standard", "TabWidth", "UseTab"
]

st_encodings_trans = {
   "UTF-8" : "utf-8",
   "UTF-8 with BOM" : "utf-8-sig",
   "UTF-16 LE" : "utf-16-le",
   "UTF-16 LE with BOM" : "utf-16",
   "UTF-16 BE" : "utf-16-be",
   "UTF-16 BE with BOM" : "utf-16",
   "Western (Windows 1252)" : "cp1252",
   "Western (ISO 8859-1)" : "iso8859-1",
   "Western (ISO 8859-3)" : "iso8859-3",
   "Western (ISO 8859-15)" : "iso8859-15",
   "Western (Mac Roman)" : "mac-roman",
   "DOS (CP 437)" : "cp437",
   "Arabic (Windows 1256)" : "cp1256",
   "Arabic (ISO 8859-6)" : "iso8859-6",
   "Baltic (Windows 1257)" : "cp1257",
   "Baltic (ISO 8859-4)" : "iso8859-4",
   "Celtic (ISO 8859-14)" : "iso8859-14",
   "Central European (Windows 1250)" : "cp1250",
   "Central European (ISO 8859-2)" : "iso8859-2",
   "Cyrillic (Windows 1251)" : "cp1251",
   "Cyrillic (Windows 866)" : "cp866",
   "Cyrillic (ISO 8859-5)" : "iso8859-5",
   "Cyrillic (KOI8-R)" : "koi8-r",
   "Cyrillic (KOI8-U)" : "koi8-u",
   "Estonian (ISO 8859-13)" : "iso8859-13",
   "Greek (Windows 1253)" : "cp1253",
   "Greek (ISO 8859-7)" : "iso8859-7",
   "Hebrew (Windows 1255)" : "cp1255",
   "Hebrew (ISO 8859-8)" : "iso8859-8",
   "Nordic (ISO 8859-10)" : "iso8859-10",
   "Romanian (ISO 8859-16)" : "iso8859-16",
   "Turkish (Windows 1254)" : "cp1254",
   "Turkish (ISO 8859-9)" : "iso8859-9",
   "Vietnamese (Windows 1258)" :  "cp1258",
   "Hexadecimal" : None,
   "Undefined" : None
}


kl_temp_replace = [
    "public",
    "private",
    "protected",
    "([A-Za-z0-9]*[?!])\\("
]

kl_fix_subs = [
    ("!= =", "!=="),
    ("== =", "==="),
]


# Check if we are running on a Windows operating system
os_is_windows = os.name == 'nt'


# The default name of the clang-format executable
default_binary = 'clang-format.exe' if os_is_windows else 'clang-format'


# This function taken from Stack Overflow response:
# http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None


# Set the path to the binary in the settings file.
def set_path(path):
    settings = sublime.load_settings(settings_file)
    settings.set('binary', path)
    sublime.save_settings(settings_file)
    # Make sure the globals are updated.
    load_settings()


# We avoid dependencies on yaml, since the output we need is very simple.
def dic_to_yaml_simple(d):
    output = ""
    n      = len(d)
    for k in d:
        output += str(k)
        output += ": "
        if type(d[k]) is bool:
            output += str(d[k]).lower()
        else:
            output += str(d[k])
        n -= 1
        if (n!=0):
            output += ', '
    return output


# We store a set of customised values in a sublime settings file, so that it is
# possible to very quickly customise the output.
# This function returns the correct customised style tag.
def load_custom():
    custom_settings = sublime.load_settings(custom_style_settings)
    keys = dict()
    for v in all_settings:
        result = custom_settings.get(v, None)
        if result != None:
            keys[v] = result
    out = "-style={" + dic_to_yaml_simple(keys) + "}"

    return out


# Display input panel to update the path.
def update_path():
    load_settings()
    w = sublime.active_window()
    w.show_input_panel("Path to clang-format: ", binary, set_path, None, None)


# Check that the binary can be found and is executable.
def check_binary():
    # If we couldn't find the binary.
    if (which(binary) == None):
        # Try to guess the correct setting.
        if (which(default_binary) != None):
            # Looks like clang-format is in the path, remember that.
            set_path(default_binary)
            return True
        # We suggest setting a new path using an input panel.
        msg = "The clang-format binary was not found. Set a new path?"
        if sublime.ok_cancel_dialog(msg):
            update_path()
            return True
        else:
            return False
    return True


# Load settings and put their values into global scope.
# Probably a nicer way of doing this, but it's simple enough and it works fine.
def load_settings():
    # We set these globals.
    global binary
    global style
    global format_on_save
    global languages
    settings_global = sublime.load_settings(settings_file)
    settings_local = sublime.active_window().active_view().settings().get('ClangFormat', {})
    load = lambda name, default: settings_local.get(name, settings_global.get(name, default))
    # Load settings, with defaults.
    binary         = load('binary', default_binary)
    style          = load('style', styles[0])
    format_on_save = load('format_on_save', False)
    languages      = load('languages', ['C', 'C++', 'C++11', 'JavaScript'])


def is_supported(lang):
    load_settings()
    return any((lang.endswith((l + '.tmLanguage', l + '.sublime-syntax')) for l in languages))


ViewState = namedtuple('ViewState', ['row', 'col', 'vector'])

def save_state(view):
    # save cursor position
    row, col = view.rowcol(view.sel()[0].begin())
    # save viewport
    vector = view.text_to_layout(view.visible_region().begin())
    return ViewState(row, col, vector)

def restore_state(view, state):
    # restore cursor position
    sel = view.sel()
    if len(sel) == 1 and sel[0].a == sel[0].b:
        point = view.text_point(state.row, state.col)
        sel.subtract(sel[0])
        sel.add(sublime.Region(point, point))

    # restore viewport
    # magic, next line doesn't work without it
    view.set_viewport_position((0.0, 0.0), False)
    view.set_viewport_position(state.vector, False)


# Triggered when the user runs clang format.
class ClangFormatCommand(sublime_plugin.TextCommand):
    def kl_pre_sanitize(self, buf):
        self.kl_find_replace = []
        used = set()
        for pattern in kl_temp_replace:
            import re
            found_patterns = set(re.findall(pattern, buf))
            for found in found_patterns:
                if len(found) < 2:
                    continue
                randstr = ""
                # find a random string that hasn't been used, and isn't already in the buf. 
                while (not randstr) or (randstr in used) or (randstr in buf):
                    randstr = ''.join(random.choice(string.ascii_uppercase+string.ascii_lowercase) for x in range(len(found)))
                used.add(randstr)
                self.kl_find_replace.append((found, randstr))

        for findstr, repl in self.kl_find_replace:
            buf = buf.replace(findstr, repl)

        return buf

    def kl_post_sanitize(self, buf):
        for findstr, repl in self.kl_find_replace:
            # undo it
            buf = buf.replace(repl, findstr)

        import re
        for pattern, repl in kl_fix_subs:
            buf = re.sub(pattern, repl, buf)

        return buf


    def run(self, edit, whole_buffer=False):
        load_settings()

        if not check_binary():
            return

        sublime.status_message("Clang format (style: "+ style + ")." )

        # The below code has been taken and tweaked from llvm.
        encoding = st_encodings_trans[self.view.encoding()]
        if encoding is None:
            encoding = 'utf-8'

        # We use 'file' not 'File' when passing to the binary.
        # But all the other styles are in all caps.
        _style = style
        if style == "File":
            _style = "file"

        command = []

        if style == "Custom":
            command = [binary, load_custom()]
        else:
            command = [binary, '-style', _style]

        regions = []
        if whole_buffer:
            regions = [sublime.Region(0, self.view.size())]
        else:
            regions = self.view.sel()

        view_state = save_state(self.view)

        if all(x.size() == 0 for x in regions):
            # no selection, select all
            regions = [sublime.Region(0, self.view.size())]

        for region in regions:
            region_offset = region.begin()
            region_length = region.size()

            view = sublime.active_window().active_view()

            # If the command is run at the end of the line,
            # Run the command on the whole line.
            if view.classify(region_offset) & sublime.CLASS_LINE_END > 0:
                region        = view.line(region_offset)
                region_offset = region.begin()
                region_lenth  = region.size()

            command.extend(['-offset', str(region_offset),
                            '-length', str(region_length)])

        # We only set the offset once, otherwise CF complains.
        command.extend(['-assume-filename', str(self.view.file_name())] )

        # TODO: Work out what this does.
        # command.extend(['-output-replacements-xml'])

        # Run CF, and set buf to its output.
        buf = self.view.substr(sublime.Region(0, self.view.size()))
        buf = self.kl_pre_sanitize(buf)
        startupinfo = None
        if os_is_windows:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p   = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, stdin=subprocess.PIPE,
                               startupinfo=startupinfo)
        output, error = p.communicate(buf.encode(encoding))

        # Display any errors returned by clang-format using a message box,
        # instead of just printing them to the console. Also, we halt on all
        # errors: e.g. We don't just settle for using using a default style.
        if error:
            # We don't want to do anything by default.
            # If the error message tells us it is doing that, truncate it.
            default_message = ", using LLVM style"
            msg = error.decode("utf-8")
            if msg.strip().endswith(default_message):
                msg = msg[:-len(default_message)-1]
            sublime.error_message("Clang format: " + msg)
            # Don't do anything.
            return

        output = self.kl_post_sanitize(output)

        # If there were no errors, we replace the view with the outputted buf.
        self.view.replace(
            edit, sublime.Region(0, self.view.size()),
            output.decode(encoding))

        restore_state(self.view, view_state)


# Hook for on-save event, to allow application of clang-format on save.
class clangFormatEventListener(sublime_plugin.EventListener):
    def on_pre_save(self, view):
        # Only do this for supported languages
        syntax = view.settings().get('syntax')
        if is_supported(syntax):
            # Ensure that settings are up to date.
            load_settings()
            if format_on_save:
                print("Auto-applying Clang Format on save.")
                view.run_command("clang_format", {"whole_buffer": True})


# Called from the UI to update the path in the settings.
class clangFormatSetPathCommand(sublime_plugin.WindowCommand):
    def run(self):
        update_path()


# Called from the UI to set the current style.
class clangFormatSelectStyleCommand(sublime_plugin.WindowCommand):
    def done(self, i):
        settings = sublime.load_settings(settings_file)
        settings.set("style", styles[i])
        sublime.save_settings(settings_file)

    def run(self):
        load_settings()
        active_window = sublime.active_window()
        # Get current style
        try:
            sel = styles.index(style)
        except ValueError:
            sel = 0
        active_window.show_quick_panel(styles, self.done, 0, sel)


class ClangFormatFileCommand(sublime_plugin.WindowCommand):
    def run(self, paths=None, preview=True):
        if paths:
            self.opened_views = []
            self.current_preview = preview
            for path in self.files(paths):
                view = self.window.open_file(path)
                self.opened_views.append(view)

        if any(x.is_loading() for x in self.opened_views):
            sublime.set_timeout(self.run, 50)
        else:
            for view in self.opened_views:
                # view = self.window.open_file(path)
                format_command = ClangFormatCommand(view)
                edit = view.begin_edit("edit file")
                format_command.run(edit, True)
                view.end_edit(edit)
                if not self.current_preview:
                    view.run_command('save')
            self.opened_views = []

    def py_files_from_dir(self, path):
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                if filename.endswith('.kl'):
                    yield os.path.join(dirpath, filename)

    def files(self, paths):
        for path in paths:
            if os.path.isfile(path) and path.endswith('.kl'):
                yield path
                continue
            if os.path.isdir(path):
                for file_path in self.py_files_from_dir(path):
                    yield file_path

    def check_paths(self, paths):
        files = self.files(paths)
        if files:
            return True
        else:
            return False

    def is_enabled(self, *args, **kwd):
        return self.check_paths(kwd.get('paths'))

    def is_visible(self, *args, **kwd):
        return True