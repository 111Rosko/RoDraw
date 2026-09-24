"""Bulgarian."""
STRINGS = {
    "tool.select.name": "Избор / местене",
    "tool.select.hint": "Хванете надпис или фигура и я преместете; Delete я изтрива",
    "tool.pen.name": "Писалка",
    "tool.pen.hint": "Рисуване на ръка",
    "tool.highlighter.name": "Маркер",
    "tool.highlighter.hint": "Широка полупрозрачна линия",
    "tool.eraser.name": "Гума",
    "tool.eraser.hint": "Изтрива само това, през което минете",
    "tool.line.name": "Линия",
    "tool.line.hint": "Права линия; задръжте Shift за стъпка от 45 градуса",
    "tool.arrow.name": "Стрелка",
    "tool.arrow.hint": "Посочва на учениците важното",
    "tool.rect.name": "Правоъгълник",
    "tool.rect.hint": "Оградете област; задръжте Shift за квадрат",
    "tool.ellipse.name": "Елипса",
    "tool.ellipse.hint": "Заградете област; задръжте Shift за кръг",
    "tool.text.name": "Текст",
    "tool.text.hint": "Щракнете и напишете надпис",
    "tool.laser.name": "Лазерна показалка",
    "tool.laser.hint": "Точка, която следва курсора; кликовете стигат до приложенията",
    "tool.spotlight.name": "Прожектор",
    "tool.spotlight.hint": "Затъмнява всичко без един кръг; кликовете стигат до приложенията",
    "tool.zoom.name": "Увеличение на област",
    "tool.zoom.hint": 'Очертайте кутия, за да я увеличите; после колелцето мести, Ctrl+колелце приближава',

    "bar.move.name": "Преместване на лентата",
    "bar.move.hint": "Влачете ме където искате",
    "bar.colour.name": "Цвят {colour}",
    "bar.colour.hint": "Писалката, фигурите и текстът използват този цвят",
    "bar.size.name": "Размер",
    "bar.size.hint": "Колко дебело рисува текущият инструмент; колелцето също работи",
    "bar.undo.name": "Отмяна",
    "bar.undo.hint": "Връща последното нарисувано",
    "bar.redo.name": "Повтаряне",
    "bar.redo.hint": "Връща го обратно",
    "bar.clear.name": "Изчистване",
    "bar.clear.hint": "Изтрива всички надписи от всички екрани",
    "bar.screens.name": "Екрани",
    "bar.screens.hint": "Изберете на кои монитори да се рисува",
    "bar.board.name": "Бяла дъска",
    "bar.board.hint": "Плътен фон на този екран; {key} за черна",
    "bar.save.name": "Запазване на снимка",
    "bar.save.hint": "Записва PNG в папката Картини",
    "bar.settings.name": "Настройки",
    "bar.settings.hint": "Бутон за заспиване, размери, цветове, клавиши",
    "bar.sleep.name": "Заспиване",
    "bar.wake.name": "Събуждане",
    "bar.sleep.hint": "Пропуска всички кликове към приложенията; рисунките остават на екрана",
    "bar.quit.name": "Изход от RoDraw",

    # -- touch boards: on-screen replacements for the wheel and Esc
    "bar.escape.name": "Назад",
    "bar.escape.hint": "Излиза от увеличение, прожектор или дъска — същото като Esc",
    "bar.zoomout.name": "Намаляване",
    "bar.zoomin.name": "Увеличаване",
    "bar.zoompan.name": "Местене на изгледа",
    "bar.zoompan.hint": "Влачете където и да е по екрана, за да местите увеличения изглед",
    "bar.zoomexit.name": "Затваряне на увеличението",
    "set.general.touch": "Режим за тъчскрийн",
    "set.general.touch.hint": "По-едри бутони, за пръст",
    "set.touch.auto": "Автоматично",
    "set.touch.on": "Винаги включен",
    "set.touch.off": "Изключен",

    # -- the shape and size of the bar itself
    "set.general.barlayout": "Форма на лентата",
    "set.layout.bar": "Една дълга лента",
    "set.layout.compact": "Компактен блок",
    "set.general.barlayout.hint": "Блокът стои в ъгъла, където го достига и ученик, който не стига до горния край на дъската",
    "set.general.barscale": "Големина на лентата",
    "set.general.barscale.hint": "Процент от нормалната големина, ако бутоните излизат твърде малки или твърде големи",

    "tray.sleep": "Заспиване",
    "tray.wake": "Събуждане",
    "tray.screens": "Екрани...",
    "tray.clear": "Изчистване на надписите",
    "tray.settings": "Настройки...",
    "tray.quit": "Изход от RoDraw",
    "tray.ready": "RoDraw — готов",
    "tray.asleep": "RoDraw — заспал",

    "msg.ready": "RoDraw е готов — натиснете {key} за заспиване",
    "msg.start_asleep": "RoDraw спи — натиснете {key}, за да рисувате",
    "msg.asleep": "Заспал — кликовете преминават. {key} за събуждане",
    "msg.awake": "Буден — готов за рисуване",
    "msg.cleared": "Изчистено",
    "msg.zoom_on": 'Увеличение {scale}x — колелцето мести, Esc излиза',
    "msg.zoom_off": "Увеличението е изключено",
    "msg.zoom_small": "Областта е твърде малка",
    "msg.zoom_refreshed": "Изображението е обновено",
    "msg.colour": "Цвят {colour}",
    "msg.size": "{tool} — размер {size}",
    "msg.saved": "Запазено в Картини\\RoDraw\\{name}",
    "msg.save_failed": "Снимката не можа да бъде запазена",
    "msg.copied": "Снимката е копирана",
    "msg.settings_saved": "Настройките са запазени",
    "msg.hotkey_failed": "Windows не даде бутона {key} на RoDraw — може би друга "
                         "програма вече го използва. Изберете друг в Настройки.",
    "msg.screen_on": "Рисуване върху {screen}",
    "msg.screen_off": "Без намеса: {screen}",
    "msg.screen_last": "Поне един екран трябва да остане включен",
    "msg.lang_changed": "Езикът е сменен — отворете Настройки отново, за да се преведат и там",

    "screen.label": "Екран {index}: {width}x{height}",
    "screen.main": " (основен)",
    "screen.menu": "На кои екрани да се рисува?",

    "set.title": "Настройки на RoDraw",
    "set.tab.general": "Общи",
    "set.tab.drawing": "Рисуване",
    "set.tab.keys": "Клавиши",
    "set.tab.about": "За програмата",
    "set.save": "Запазване",
    "set.cancel": "Отказ",

    "set.lang.group": "Език",
    "set.lang.label": "Език на интерфейса:",
    "set.lang.hint": "Важи за лентата, менютата и съобщенията на екрана.",

    "set.sleep.group": "Режим на заспиване",
    "set.sleep.button": "Бутон за заспиване / събуждане:",
    "set.sleep.hint": "Този бутон се регистрира в цялата система, затова работи дори "
                      "когато RoDraw спи и друга програма е активна. Функционалните "
                      "клавиши (F8, F9...) и комбинации като Ctrl+Alt+D са най-безопасни "
                      "— обикновена буква би била отнета от всички останали програми.",
    "set.sleep.keep": "Надписите да остават на екрана при заспиване",
    "set.sleep.fade": "Избледняване на надписите при заспиване",
    "set.sleep.start": "RoDraw да стартира заспал",
    "set.sleep.bad_key": "Windows не може да регистрира „{key}“ като глобален бутон. "
                         "Опитайте функционален клавиш или комбинация с Ctrl / Alt.",
    "set.sleep.plain_key": "„{key}“ ще бъде отнеман от всяка програма, докато RoDraw работи.",
    "set.sleep.need_key": "Режимът на заспиване има нужда от бутон. Изберете такъв преди запазване.",
    "set.sleep.refused": "Windows не може да регистрира „{key}“ като системен бутон.\n\n"
                         "Опитайте функционален клавиш като F8 или комбинация като Ctrl+Alt+D.",

    "set.ui.group": "Интерфейс",
    "set.ui.toolbar": "Показване на плаващата лента",
    "set.ui.cursor": "Кръг около курсора с размера на четката",
    "set.ui.startup": "RoDraw да се стартира при влизане в Windows",

    "set.sizes.group": "Размери по подразбиране",
    "set.sizes.pen": "Писалка:",
    "set.sizes.highlighter": "Маркер:",
    "set.sizes.eraser": "Гума:",
    "set.sizes.shape": "Линии, стрелки и фигури:",
    "set.sizes.font": "Размер на текста:",
    "set.fill": "Запълване на правоъгълниците и елипсите",
    "set.eraser_whole": "Гумата да изтрива цялата линия, вместо само частта под нея",

    "set.palette.group": "Палитра",
    "set.palette.hint": "Щракнете върху цвят, за да го смените. Числото отгоре е неговият клавиш.",
    "set.palette.pick": "Цвят номер {index}",
    "set.palette.tip": "Цвят номер {index} — натиснете {index} докато рисувате",

    "set.keys.intro": "Щракнете в полето и натиснете желаните клавиши. Единичните букви "
                      "работят като обикновено натискане, докато RoDraw е буден.",
    "set.keys.restore": "Връщане на клавишите по подразбиране",
    "set.keys.unassign": "Премахване",
    "set.keys.clash": "Повтарящи се клавиши (ще работи само първият): {list}",

    "set.about.body":
        "<h2>RoDraw</h2>"
        "<p>Рисувайте директно върху екрана, за да видят учениците точно къде да гледат.</p>"
        "<p><b>Режимът на заспиване</b> прави RoDraw прозрачен за мишката: надписите "
        "остават на екрана, но всеки клик отива към програмата отдолу. Натиснете "
        "бутона отново, за да продължите да рисувате.</p>"
        "<p><b>Увеличението на област</b> замразява екрана и увеличава кутията, която "
        "очертаете. Колелцето променя мащаба, средният бутон движи изгледа, Esc излиза.</p>"
        "<p style='color:#9AA4AF'>Настройките се пазят в "
        "<code>%APPDATA%\\RoDraw\\settings.json</code>.</p>",

    "keys.group.tools": "Инструменти",
    "keys.group.edit": "Редактиране",
    "keys.group.view": "Изглед",
    "keys.group.brush": "Четка",
    "keys.group.colours": "Цветове",
    "keys.group.app": "Програма",

    "keys.edit.undo": "Отмяна",
    "keys.edit.redo": "Повтаряне",
    "keys.edit.redo_alt": "Повтаряне (друг клавиш)",
    "keys.edit.clear": "Изчистване на всички надписи",
    "keys.edit.delete": "Изтриване на избраното",
    "keys.edit.save": "Запазване на снимка в Картини",
    "keys.edit.copy": "Копиране на снимка",
    "keys.view.zoom_in": "Увеличаване",
    "keys.view.zoom_out": "Намаляване",
    "keys.view.zoom_reset": "Нулиране на увеличението",
    "keys.view.refresh": "Обновяване на замразеното изображение",
    "keys.view.whiteboard": "Бял фон",
    "keys.view.blackboard": "Черен фон",
    "keys.brush.bigger": "По-голям размер",
    "keys.brush.smaller": "По-малък размер",
    "keys.colour.slot": "Цвят номер {index}",
    "keys.app.toolbar": "Показване / скриване на лентата",
    "keys.app.settings": "Отваряне на настройките",
    "keys.app.quit": "Изход от RoDraw",

    "app.running": "RoDraw вече работи.\n\nПотърсете иконата му в областта за "
                   "уведомяване, до часовника.",

    # -- colour picker
    "colour.title": 'Цвят номер {index}',
    "colour.hex": 'Шестнадесетичен:',
    "colour.recent": 'Използвани наскоро',
    "colour.recent.none": 'Още няма — смесените от вас цветове ще се събират тук.',
    "colour.reset": 'Връщане на осемте цвята по подразбиране',
    "colour.reset.hint": 'Наскоро използваните цветове се запазват',
    "colour.ok": 'Използвай този цвят',
    "msg.colour_changed": 'Цвят номер {index} вече е {colour}',
    "msg.palette_reset": 'Палитрата е върната — наскоро използваните цветове са запазени',
    "bar.colour.doubleclick": 'Щракнете двукратно върху цвят, за да смесите свой',

    # -- quick exit
    "keys.app.escape": 'Изход от увеличение, прожектор или дъска',
    "msg.escaped": 'Обратно към нормалното',
}
