# Regression fixture

`ikim-2026-11-16.xls` is the unmodified public ИКиМ.xls downloaded on
2026-11-14 from the official public folder `16.11-21.11`:
https://disk.yandex.ru/d/Xc08g8WbTavdHQ

The college links this folder at:
https://mck72.ru/learners/information-on-learning-process/training-schedules/

Size: 100864 bytes. SHA-256:
`b45971b7ede6f195d5b8af92c61f2ef2c414aa389a17a20cc621488b459eb1e9`

Sheet `ДЗ; ДПИ`, U29:U31: styled blank cells (MULBLANK, BIFF 0x00BE).
The old parser interpreted XF formatting indexes as RK values and produced
`2.22518929507823e-307`. This fixture tests the actual binary parsing path,
not only sanitization of already corrupted JSON. Other ordinary downloads
remain untracked. The file contains public academic schedules.
