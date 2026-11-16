import React, { useState } from 'react';
import { Bot, Save, ShieldAlert, CheckCircle2, AlertCircle, ExternalLink, RefreshCw, Send, Sliders } from 'lucide-react';
import { BotSettings, ModerationResult } from '../types';

interface BotSettingsViewProps {
  settings: BotSettings;
  onUpdateSettings: (newSettings: Partial<BotSettings>) => Promise<void>;
  onTestPhrase: (phrase: string) => Promise<ModerationResult | null>;
}

export function BotSettingsView({ settings, onUpdateSettings, onTestPhrase }: BotSettingsViewProps) {
  const [formData, setFormData] = useState<BotSettings>({ ...settings });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Telegram bot token test
  const [botToken, setBotToken] = useState('');
  const [tokenStatus, setTokenStatus] = useState<{ loading: boolean; success?: boolean; message?: string }>({
    loading: false,
  });

  // Direct analyzer playground test
  const [testPhrase, setTestPhrase] = useState('');
  const [testResult, setTestResult] = useState<ModerationResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  // Telegram polling & conflict state
  const [telegramStatus, setTelegramStatus] = useState<{
    connected?: boolean;
    botName?: string;
    isPolling?: boolean;
    conflict?: boolean;
    consecutiveConflicts?: number;
    lastError?: string;
  }>({});
  const [pollingLoading, setPollingLoading] = useState(false);
  const [pollingNotice, setPollingNotice] = useState<string | null>(null);
  const [copiedWebhook, setCopiedWebhook] = useState(false);

  const fetchTelegramStatus = React.useCallback(async () => {
    try {
      const res = await fetch('/api/telegram/status');
      const data = await res.json();
      setTelegramStatus(data);
    } catch {
      // Ignore network errors
    }
  }, []);

  React.useEffect(() => {
    fetchTelegramStatus();
    const interval = setInterval(fetchTelegramStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchTelegramStatus]);

  const handleStartPolling = async () => {
    setPollingLoading(true);
    try {
      const res = await fetch('/api/telegram/start-polling', { method: 'POST' });
      const data = await res.json();
      setPollingNotice(data.message || 'Long Polling запущен');
      await fetchTelegramStatus();
      setTimeout(() => setPollingNotice(null), 4000);
    } catch (e: any) {
      setPollingNotice('Ошибка запуска Polling');
      setTimeout(() => setPollingNotice(null), 4000);
    } finally {
      setPollingLoading(false);
    }
  };

  const handleStopPolling = async () => {
    setPollingLoading(true);
    try {
      const res = await fetch('/api/telegram/stop-polling', { method: 'POST' });
      const data = await res.json();
      setPollingNotice(data.message || 'Long Polling остановлен');
      await fetchTelegramStatus();
      setTimeout(() => setPollingNotice(null), 4000);
    } catch (e: any) {
      setPollingNotice('Ошибка остановки Polling');
      setTimeout(() => setPollingNotice(null), 4000);
    } finally {
      setPollingLoading(false);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      await onUpdateSettings(formData);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  const handleConnectTelegram = async () => {
    if (!botToken.trim()) return;
    setTokenStatus({ loading: true });
    try {
      const res = await fetch('/api/telegram/set-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: botToken }),
      });
      const data = await res.json();
      if (data.success) {
        setTokenStatus({
          loading: false,
          success: true,
          message: `Успешно подключен бот @${data.botName}!`,
        });
        setFormData((prev) => ({
          ...prev,
          realTelegramConnected: true,
          telegramBotUsername: data.botName,
        }));
        await fetchTelegramStatus();
      } else {
        setTokenStatus({
          loading: false,
          success: false,
          message: data.error || 'Не удалось подключиться к Telegram API.',
        });
      }
    } catch (err: any) {
      setTokenStatus({ loading: false, success: false, message: err.message });
    }
  };

  const handleRunTestPhrase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testPhrase.trim() || isTesting) return;
    setIsTesting(true);
    try {
      const res = await onTestPhrase(testPhrase);
      setTestResult(res);
    } finally {
      setIsTesting(false);
    }
  };

  const currentWebhookUrl = typeof window !== 'undefined' ? `${window.location.origin}/api/telegram/webhook` : '';

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Moderation Rules & Scoring Settings */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Sliders className="w-5 h-5 text-indigo-600" />
            <div>
              <h3 className="text-sm font-bold text-slate-900">Параметры модерации и авто-блокировок</h3>
              <p className="text-xs text-slate-500">
                Пороги кумулятивного рейтинга и автоматические санкции для нарушителей
              </p>
            </div>
          </div>

          {saveSuccess && (
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-2.5 py-1 rounded-full flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Настройки сохранены
            </span>
          )}
        </div>

        <form onSubmit={handleSaveSettings} className="p-5 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Mute threshold */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-700 flex items-center justify-between">
                <span>Порог авто-мута (отрицательный рейтинг):</span>
                <span className="text-rose-600 font-extrabold">{formData.muteThreshold}</span>
              </label>
              <input
                type="range"
                min="-30"
                max="-3"
                step="1"
                value={formData.muteThreshold}
                onChange={(e) => setFormData({ ...formData, muteThreshold: Number(e.target.value) })}
                className="w-full accent-rose-600 cursor-pointer"
              />
              <p className="text-[11px] text-slate-500">
                Когда накопленная карма участника опустится до {formData.muteThreshold}, робот автоматически применит временный мут.
              </p>
            </div>

            {/* Mute duration */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-700">
                Длительность временного мута:
              </label>
              <select
                value={formData.muteDurationMinutes}
                onChange={(e) => setFormData({ ...formData, muteDurationMinutes: Number(e.target.value) })}
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500 font-medium text-slate-800"
              >
                <option value={30}>30 минут</option>
                <option value={60}>1 час</option>
                <option value={120}>2 часа (Рекомендуется)</option>
                <option value={360}>6 часов</option>
                <option value={720}>12 часов</option>
                <option value={1440}>24 часа (1 сутки)</option>
              </select>
              <p className="text-[11px] text-slate-500">
                По истечении срока статус пользователя автоматически вернется в активный.
              </p>
            </div>

            {/* Ban threshold */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-700 flex items-center justify-between">
                <span>Порог перманентного бана (критический рейтинг):</span>
                <span className="text-rose-700 font-extrabold">{formData.banThreshold}</span>
              </label>
              <input
                type="range"
                min="-50"
                max="-15"
                step="1"
                value={formData.banThreshold}
                onChange={(e) => setFormData({ ...formData, banThreshold: Number(e.target.value) })}
                className="w-full accent-rose-700 cursor-pointer"
              />
              <p className="text-[11px] text-slate-500">
                Бессрочный запрет отправки сообщений (режим «Только чтение» без удаления из чата) при падении кармы до {formData.banThreshold}.
              </p>
            </div>

            {/* AI Provider & Model Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-700">Провайдер ИИ:</label>
              <select
                value={formData.aiProvider || 'google'}
                onChange={(e) => {
                  const provider = e.target.value as 'google' | 'yandex';
                  const defaultModel = provider === 'yandex' ? 'yandexgpt-5.1' : 'gemini-2.5-flash';
                  setFormData({ ...formData, aiProvider: provider, aiModelName: formData.aiModelName || defaultModel });
                }}
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500 font-medium text-slate-800"
              >
                <option value="google">Google (Gemini AI)</option>
                <option value="yandex">Yandex (YandexGPT / alice.yandex.ru)</option>
              </select>
              <p className="text-[11px] text-slate-500">
                Выберите языковую модель для анализа сообщений (Google по умолчанию).
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-700">Название модели:</label>
              <input
                type="text"
                value={formData.aiModelName || (formData.aiProvider === 'yandex' ? 'yandexgpt-5.1' : 'gemini-2.5-flash')}
                onChange={(e) => setFormData({ ...formData, aiModelName: e.target.value })}
                placeholder={formData.aiProvider === 'yandex' ? 'yandexgpt-5.1' : 'gemini-2.5-flash'}
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500 font-medium text-slate-800"
              />
              <p className="text-[11px] text-slate-500">
                Имя модели ИИ (например, gemini-2.5-flash или yandexgpt-5.1).
              </p>
            </div>

            {/* Auto-delete profanity switch */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-slate-700">Автоматические действия:</span>
              <div className="space-y-2">
                <label className="flex items-center gap-2.5 text-xs text-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.autoDeleteProfanity}
                    onChange={(e) => setFormData({ ...formData, autoDeleteProfanity: e.target.checked })}
                    className="w-4 h-4 rounded text-indigo-600 accent-indigo-600"
                  />
                  <span>Удалять сообщения с ненормативной лексикой</span>
                </label>

                <label className="flex items-start gap-2.5 text-xs text-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.commentProfanityMessages ?? true}
                    onChange={(e) => setFormData({ ...formData, commentProfanityMessages: e.target.checked })}
                    className="w-4 h-4 mt-0.5 rounded text-indigo-600 accent-indigo-600"
                  />
                  <div>
                    <span className="font-medium">Комментировать сообщения с ненормативной лексикой</span>
                    <span className="block text-[11px] text-slate-500 font-normal">
                      После удаления матерного сообщения бот выдает краткий комментарий без показа запрещенного слова.
                    </span>
                  </div>
                </label>

                <label className="flex items-start gap-2.5 text-xs text-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.commentToxicMessages ?? true}
                    onChange={(e) => setFormData({ ...formData, commentToxicMessages: e.target.checked })}
                    className="w-4 h-4 mt-0.5 rounded text-indigo-600 accent-indigo-600"
                  />
                  <div>
                    <span className="font-medium">Комментировать токсичные сообщения</span>
                    <span className="block text-[11px] text-slate-500 font-normal">
                      При обнаружении токсичности бот выводит предупреждающий баннер-комментарий, сообщение не удаляется.
                    </span>
                  </div>
                </label>

                <label className="flex items-start gap-2.5 text-xs text-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.commentNeutralMessages ?? false}
                    onChange={(e) => setFormData({ ...formData, commentNeutralMessages: e.target.checked })}
                    className="w-4 h-4 mt-0.5 rounded text-indigo-600 accent-indigo-600"
                  />
                  <div>
                    <span className="font-medium">Комментировать нейтральные сообщения</span>
                    <span className="block text-[11px] text-slate-500 font-normal">
                      По умолчанию отключено: бот не пишет комментарии и не спамит в чат на обычные диалоги.
                    </span>
                  </div>
                </label>
              </div>
            </div>
          </div>

          <div className="pt-3 border-t border-slate-100 flex justify-end">
            <button
              type="submit"
              disabled={isSaving}
              className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-bold hover:bg-indigo-700 active:scale-95 transition-all shadow-sm flex items-center gap-1.5"
            >
              <Save className="w-4 h-4" />
              <span>{isSaving ? 'Сохранение...' : 'Сохранить настройки'}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Real Telegram Bot Setup */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Bot className="w-5 h-5 text-sky-500" />
            <div>
              <h3 className="text-sm font-bold text-slate-900">Интеграция с реальным Telegram чатом</h3>
              <p className="text-xs text-slate-500">
                Подключение бота через официальный Telegram Bot API
              </p>
            </div>
          </div>

          <span
            className={`text-xs font-semibold px-2.5 py-1 rounded-full flex items-center gap-1 ${
              formData.realTelegramConnected
                ? 'bg-emerald-100 text-emerald-800'
                : 'bg-slate-100 text-slate-600'
            }`}
          >
            {formData.realTelegramConnected ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                @{formData.telegramBotUsername || 'Бот подключен'}
              </>
            ) : (
              'Не подключен'
            )}
          </span>
        </div>

        <div className="p-5 space-y-4">
          <div className="p-3.5 rounded-xl bg-sky-50/70 border border-sky-200 text-xs text-sky-950 space-y-1.5">
            <div className="font-bold flex items-center gap-1 text-sky-900">
              <ExternalLink className="w-3.5 h-3.5" />
              Инструкция по подключению в 3 шага:
            </div>
            <ol className="list-decimal list-inside space-y-1 text-[11px] text-sky-800 font-normal">
              <li>Откройте Telegram и напишите боту <b>@BotFather</b> команду <code>/newbot</code>.</li>
              <li>Скопируйте полученный HTTP API Token и вставьте в поле ниже.</li>
              <li>Добавьте вашего бота в ваш Telegram-чат и назначьте его <b>Администратором</b> (права: удаление сообщений, блокировка участников).</li>
            </ol>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-700">Telegram Bot Token (из @BotFather):</label>
            <div className="flex items-center gap-2">
              <input
                type="password"
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                placeholder="1234567890:ABCdefGHIjklmnOPQRstuvWXyz..."
                className="flex-1 px-3.5 py-2 text-xs bg-slate-50 border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500 font-mono text-slate-900"
              />
              <button
                type="button"
                onClick={handleConnectTelegram}
                disabled={!botToken.trim() || tokenStatus.loading}
                className="px-4 py-2 bg-sky-600 text-white rounded-xl text-xs font-bold hover:bg-sky-700 active:scale-95 transition-all disabled:opacity-50 flex items-center gap-1.5"
              >
                {tokenStatus.loading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                Проверить токен
              </button>
            </div>

            {tokenStatus.message && (
              <div
                className={`text-xs p-2.5 rounded-lg flex items-center gap-1.5 ${
                  tokenStatus.success
                    ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                    : 'bg-rose-50 text-rose-800 border border-rose-200'
                }`}
              >
                {tokenStatus.success ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-rose-600" />
                )}
                <span>{tokenStatus.message}</span>
              </div>
            )}
          </div>

          {/* Polling Notice / Toast */}
          {pollingNotice && (
            <div className="text-xs p-2.5 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-900 flex items-center gap-2 animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0" />
              <span>{pollingNotice}</span>
            </div>
          )}

          {/* Conflict Detected Alert Banner */}
          {telegramStatus.conflict && (
            <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-300 text-xs text-amber-950 space-y-2">
              <div className="flex items-center gap-2 font-bold text-amber-900">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Обнаружен конфликт: Запущен другой экземпляр бота (409 Conflict)</span>
              </div>
              <p className="text-[11px] text-amber-900 leading-relaxed">
                Telegram сообщил: <i>"{telegramStatus.lastError || 'terminated by other getUpdates request'}"</i>.
                <br />
                Это означает, что бот с данным токеном уже опрашивает сообщения в другой программе или терминале.
                Чтобы получать сообщения здесь, закройте другие копии бота и нажмите <b>«Перезапустить Polling»</b>.
              </p>
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  disabled={pollingLoading}
                  onClick={handleStartPolling}
                  className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold transition-colors flex items-center gap-1.5 shadow-xs"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${pollingLoading ? 'animate-spin' : ''}`} />
                  Перезапустить Polling
                </button>
                <button
                  type="button"
                  disabled={pollingLoading}
                  onClick={handleStopPolling}
                  className="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-800 rounded-lg text-xs font-semibold transition-colors"
                >
                  Приостановить опрос
                </button>
              </div>
            </div>
          )}

          {/* Connection Mode Info */}
          <div
            className={`p-3.5 rounded-xl border text-xs space-y-2 ${
              telegramStatus.isPolling
                ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                : 'bg-slate-50 border-slate-200 text-slate-800'
            }`}
          >
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2 font-bold">
                {telegramStatus.isPolling ? (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping"></span>
                    <span>Режим соединения: Активный Long Polling (Онлайн)</span>
                  </>
                ) : (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-slate-400"></span>
                    <span>Режим соединения: Long Polling приостановлен</span>
                  </>
                )}
              </div>
              <div className="flex items-center gap-2">
                {telegramStatus.isPolling ? (
                  <>
                    <button
                      type="button"
                      disabled={pollingLoading}
                      onClick={handleStartPolling}
                      className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-2xs transition-colors flex items-center gap-1"
                    >
                      <RefreshCw className={`w-3 h-3 ${pollingLoading ? 'animate-spin' : ''}`} />
                      <span>Синхронизировать сейчас</span>
                    </button>
                    <button
                      type="button"
                      disabled={pollingLoading}
                      onClick={handleStopPolling}
                      className="px-3 py-1 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-xs font-semibold transition-colors"
                    >
                      Остановить
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={pollingLoading}
                    onClick={handleStartPolling}
                    className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-2xs transition-colors flex items-center gap-1"
                  >
                    <RefreshCw className={`w-3 h-3 ${pollingLoading ? 'animate-spin' : ''}`} />
                    <span>Запустить Polling</span>
                  </button>
                )}
              </div>
            </div>
            <p
              className={`text-[11px] leading-relaxed ${
                telegramStatus.isPolling ? 'text-emerald-800' : 'text-slate-500'
              }`}
            >
              {telegramStatus.isPolling
                ? 'Бот автоматически непрерывно забирает входящие сообщения из вашей группы Telegram без необходимости открывать сетевые порты или регистрировать внешние вебхуки.'
                : 'Опрос Telegram приостановлен. Нажмите «Запустить Polling», чтобы возобновить прием сообщений из группы.'}
            </p>
          </div>

          {/* Webhook information */}
          <div className="space-y-1.5 pt-2 border-t border-slate-100">
            <label className="text-xs font-bold text-slate-700">Альтернатива: Webhook URL (для собственного сервера VPS):</label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={currentWebhookUrl}
                className="flex-1 px-3 py-2 text-xs bg-slate-100 border border-slate-200 rounded-xl font-mono text-slate-600 select-all"
              />
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(currentWebhookUrl);
                  setCopiedWebhook(true);
                  setTimeout(() => setCopiedWebhook(false), 2500);
                }}
                className="px-3 py-2 bg-slate-200 text-slate-800 rounded-xl text-xs font-semibold hover:bg-slate-300 transition-colors flex items-center gap-1.5"
              >
                {copiedWebhook ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Скопировано!</span>
                  </>
                ) : (
                  <span>Копировать</span>
                )}
              </button>
            </div>
            <p className="text-[11px] text-slate-400">
              Используйте этот URL при переносе бота на собственный сервер со статическим доменом и SSL.
            </p>
          </div>
        </div>
      </div>

      {/* Direct AI Moderation Test Playground */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 bg-slate-50/50">
          <h3 className="text-sm font-bold text-slate-900">Интерактивный тестер фраз (Gemini AI Playground)</h3>
          <p className="text-xs text-slate-500">
            Проверьте, как искусственный интеллект оценивает любую фразу от -5 до +5
          </p>
        </div>

        <div className="p-5 space-y-4">
          <form onSubmit={handleRunTestPhrase} className="flex items-center gap-2">
            <input
              type="text"
              value={testPhrase}
              onChange={(e) => setTestPhrase(e.target.value)}
              placeholder="Введите любую фразу для мгновенного анализа (мат, вопрос, благодарность)..."
              className="flex-1 px-4 py-2.5 text-xs sm:text-sm bg-slate-50 border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500 text-slate-900 placeholder:text-slate-400"
            />
            <button
              type="submit"
              disabled={!testPhrase.trim() || isTesting}
              className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-bold hover:bg-indigo-700 active:scale-95 transition-all disabled:opacity-40 flex items-center gap-1.5"
            >
              {isTesting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              <span>Оценить</span>
            </button>
          </form>

          {testResult && (
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2 animate-in fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-700">Оценка фразы:</span>
                  <span
                    className={`px-2.5 py-1 rounded-full text-xs font-extrabold ${
                      testResult.score > 0
                        ? 'bg-emerald-600 text-white'
                        : testResult.score < 0
                        ? 'bg-rose-600 text-white'
                        : 'bg-slate-500 text-white'
                    }`}
                  >
                    {testResult.score > 0 ? `+${testResult.score}` : testResult.score} / 5
                  </span>
                  <span className="text-xs text-slate-500 font-medium">
                    (Тональность: {testResult.sentiment})
                  </span>
                </div>

                {testResult.profanityDetected && (
                  <span className="px-2 py-0.5 rounded bg-rose-600 text-white text-[10px] font-bold">
                    МАТ ОБНАРУЖЕН
                  </span>
                )}
              </div>

              <p className="text-xs text-slate-800 font-medium">{testResult.explanation}</p>

              {testResult.profanityWords && testResult.profanityWords.length > 0 && (
                <div className="text-[11px] text-rose-700">
                  <span className="font-bold">Найденные слова:</span> {testResult.profanityWords.join(', ')}
                </div>
              )}

              <div className="flex items-center gap-2 text-[11px] text-slate-500 pt-1">
                <span>Токсичность: {Math.round(testResult.toxicityScore * 100)}%</span>
                <span>•</span>
                <span>Рекомендуемое действие: <b>{testResult.action}</b></span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
