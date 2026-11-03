import { store } from './store';
import { analyzeMessageWithGemini } from './geminiModerator';

export class TelegramService {
  private token: string = process.env.TELEGRAM_BOT_TOKEN || '';
  private botInfo: { id: number; username: string; first_name: string } | null = null;
  private isPolling: boolean = false;
  private pollingTimeout: NodeJS.Timeout | null = null;
  private lastUpdateId: number = 0;
  private consecutiveConflicts: number = 0;
  private conflictDetected: boolean = false;
  private lastError: string | null = null;
  private currentAbortController: AbortController | null = null;
  private knownChatIds: Set<string | number> = new Set();

  constructor() {
    const pollingEnabled = process.env.TELEGRAM_POLLING_ENABLED !== 'false';
    if (this.token) {
      this.initBot().then((res) => {
        if (res.success && pollingEnabled) {
          // Add a brief delay before first poll to let any lingering connection from previous process terminate gracefully
          setTimeout(() => {
            this.startPolling();
          }, 2500);
        }
      });
    }
  }

  public setToken(newToken: string) {
    this.token = newToken.trim();
    if (this.token) {
      this.stopPolling();
      this.initBot().then((res) => {
        if (res.success && process.env.TELEGRAM_POLLING_ENABLED !== 'false') {
          setTimeout(() => this.startPolling(), 1500);
        }
      });
    } else {
      this.stopPolling();
      this.botInfo = null;
      store.updateSettings({ realTelegramConnected: false, telegramBotUsername: undefined });
    }
  }

  public getToken(): string {
    return this.token;
  }

  public getStatus() {
    return {
      connected: !!this.botInfo,
      botName: this.botInfo?.username,
      isPolling: this.isPolling,
      lastUpdateId: this.lastUpdateId,
      conflict: this.conflictDetected,
      consecutiveConflicts: this.consecutiveConflicts,
      lastError: this.lastError,
    };
  }

  public getKnownChatIds(): (string | number)[] {
    return Array.from(this.knownChatIds);
  }

  public async initBot(): Promise<{ success: boolean; botName?: string; error?: string }> {
    if (!this.token) {
      return { success: false, error: 'Токен Telegram бота не задан.' };
    }

    try {
      const res = await fetch(`https://api.telegram.org/bot${this.token}/getMe`);
      const data = await res.json();
      if (data.ok) {
        this.botInfo = data.result;
        store.updateSettings({
          realTelegramConnected: true,
          telegramBotUsername: data.result.username,
        });
        return { success: true, botName: data.result.username };
      } else {
        return { success: false, error: data.description || 'Неверный токен бота' };
      }
    } catch (e: any) {
      return { success: false, error: e.message || 'Ошибка подключения к Telegram API' };
    }
  }

  public async deleteWebhook(): Promise<{ success: boolean; description?: string }> {
    if (!this.token) return { success: false, description: 'Токен не настроен' };
    try {
      const res = await fetch(`https://api.telegram.org/bot${this.token}/deleteWebhook?drop_pending_updates=false`);
      const data = await res.json();
      return { success: data.ok, description: data.description };
    } catch (e: any) {
      return { success: false, description: e.message };
    }
  }

  public async startPolling() {
    if (this.isPolling) {
      console.log('[Telegram Polling] Polling is already active.');
      return;
    }
    if (!this.token) {
      console.log('[Telegram Polling] Cannot start: Token is not configured');
      return;
    }

    // Reset conflict status on explicit start
    this.consecutiveConflicts = 0;
    this.conflictDetected = false;
    this.lastError = null;

    if (this.pollingTimeout) {
      clearTimeout(this.pollingTimeout);
      this.pollingTimeout = null;
    }
    if (this.currentAbortController) {
      this.currentAbortController.abort();
      this.currentAbortController = null;
    }

    console.log('[Telegram Polling] Deleting any webhook to enable getUpdates Long Polling...');
    await this.deleteWebhook();

    this.isPolling = true;
    console.log('[Telegram Polling] Long Polling started successfully!');
    this.pollLoop();
  }

  public stopPolling() {
    this.isPolling = false;
    if (this.pollingTimeout) {
      clearTimeout(this.pollingTimeout);
      this.pollingTimeout = null;
    }
    if (this.currentAbortController) {
      this.currentAbortController.abort();
      this.currentAbortController = null;
    }
    console.log('[Telegram Polling] Polling stopped.');
  }

  private async pollLoop() {
    if (!this.isPolling || !this.token) return;

    this.currentAbortController = new AbortController();
    const signal = this.currentAbortController.signal;

    let shouldScheduleNext = true;
    let nextDelayMs = 1000;

    try {
      const url = `https://api.telegram.org/bot${this.token}/getUpdates?offset=${this.lastUpdateId + 1}&limit=20&timeout=4`;
      const res = await fetch(url, { signal });
      const data = await res.json();

      if (data.ok && Array.isArray(data.result)) {
        if (this.consecutiveConflicts > 0 || this.conflictDetected) {
          console.log('[Telegram Polling] getUpdates resumed successfully. Conflict resolved.');
        }
        this.consecutiveConflicts = 0;
        this.conflictDetected = false;
        this.lastError = null;

        for (const update of data.result) {
          if (update.update_id > this.lastUpdateId) {
            this.lastUpdateId = update.update_id;
          }
          await this.handleWebhookUpdate(update);
        }
        nextDelayMs = 1000;
      } else if (!data.ok) {
        const desc = typeof data.description === 'string' ? data.description : '';
        const isConflict =
          data.error_code === 409 ||
          desc.toLowerCase().includes('conflict') ||
          desc.toLowerCase().includes('terminated by other getupdates');

        if (isConflict) {
          this.consecutiveConflicts++;
          this.conflictDetected = true;
          this.lastError = desc || 'Conflict: terminated by other getUpdates request';

          if (this.consecutiveConflicts >= 4) {
            // Automatically pause polling to prevent API collision storm
            console.warn(
              `[Telegram Polling] Paused polling after ${this.consecutiveConflicts} consecutive 409 Conflict errors. Another bot instance is polling with this token. Please stop the other instance and restart polling.`
            );
            this.isPolling = false;
            shouldScheduleNext = false;
          } else {
            // Exponential backoff to allow lingering connections or the other process to clear
            nextDelayMs = Math.min(10000 * this.consecutiveConflicts, 30000);
            console.warn(
              `[Telegram Polling] Conflict detected (${this.consecutiveConflicts}/4): "${desc}". Backing off for ${nextDelayMs / 1000}s...`
            );
          }
        } else {
          console.warn('[Telegram Polling] getUpdates returned error:', desc);
          this.lastError = desc;
          nextDelayMs = 4000;
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // Expected cancellation when stopping or restarting polling
        return;
      }
      console.warn('[Telegram Polling] Loop exception:', err.message);
      nextDelayMs = 4000;
    } finally {
      this.currentAbortController = null;
    }

    if (this.isPolling && shouldScheduleNext) {
      this.pollingTimeout = setTimeout(() => this.pollLoop(), nextDelayMs);
    }
  }

  public async getWebhookInfo(): Promise<any> {
    if (!this.token) return { ok: false, error: 'Токен не настроен' };
    try {
      const res = await fetch(`https://api.telegram.org/bot${this.token}/getWebhookInfo`);
      return await res.json();
    } catch (e: any) {
      return { ok: false, error: e.message };
    }
  }

  public async setWebhook(webhookUrl: string): Promise<{ success: boolean; description?: string }> {
    if (!this.token) return { success: false, description: 'Токен не настроен' };
    try {
      // getUpdates cannot run while a webhook is active in Telegram API
      this.stopPolling();
      const res = await fetch(`https://api.telegram.org/bot${this.token}/setWebhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: webhookUrl }),
      });
      const data = await res.json();
      return { success: data.ok, description: data.description };
    } catch (err: any) {
      return { success: false, description: err.message };
    }
  }

  public async sendMessage(chatId: number | string, text: string, replyToMessageId?: number) {
    if (!this.token) return;
    try {
      await fetch(`https://api.telegram.org/bot${this.token}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text,
          reply_to_message_id: replyToMessageId,
          parse_mode: 'HTML',
        }),
      });
    } catch (err) {
      console.error('Failed to send Telegram message:', err);
    }
  }

  public async deleteMessage(chatId: number | string, messageId: number) {
    if (!this.token) return;
    try {
      await fetch(`https://api.telegram.org/bot${this.token}/deleteMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, message_id: messageId }),
      });
    } catch (err) {
      console.error('Failed to delete Telegram message:', err);
    }
  }

  public async restrictMember(chatId: number | string, userId: number | string, untilDateUnix: number) {
    if (!this.token) return;
    const isNumericId = /^\d+$/.test(String(userId));
    if (!isNumericId) return; // Skip simulator user IDs like user_103

    try {
      await fetch(`https://api.telegram.org/bot${this.token}/restrictChatMember`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          user_id: Number(userId),
          until_date: untilDateUnix,
          permissions: {
            can_send_messages: false,
            can_send_audios: false,
            can_send_documents: false,
            can_send_photos: false,
            can_send_videos: false,
            can_send_video_notes: false,
            can_send_voice_notes: false,
            can_send_polls: false,
            can_send_other_messages: false,
            can_add_web_page_previews: false,
            can_change_info: false,
            can_invite_users: false,
            can_pin_messages: false,
          },
        }),
      });
    } catch (err) {
      console.error('Failed to restrict Telegram chat member:', err);
    }
  }

  public async banMember(
    userId: number | string,
    specificChatId?: number | string
  ): Promise<{ success: boolean; chats: (number | string)[] }> {
    if (!this.token) return { success: false, chats: [] };
    const isNumericId = /^\d+$/.test(String(userId));
    if (!isNumericId) return { success: true, chats: [] };

    const chatIds = specificChatId ? [specificChatId] : Array.from(this.knownChatIds);
    const affectedChats: (number | string)[] = [];

    for (const cId of chatIds) {
      try {
        const res = await fetch(`https://api.telegram.org/bot${this.token}/banChatMember`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: cId,
            user_id: Number(userId),
          }),
        });
        const data = await res.json();
        if (data.ok) affectedChats.push(cId);
        else console.warn(`[Telegram API] banChatMember on chat ${cId} failed:`, data.description);
      } catch (err: any) {
        console.error(`[Telegram API] banChatMember error on chat ${cId}:`, err.message);
      }
    }
    return { success: affectedChats.length > 0, chats: affectedChats };
  }

  public async unbanMember(
    userId: number | string,
    specificChatId?: number | string
  ): Promise<{ success: boolean; chats: (number | string)[] }> {
    if (!this.token) return { success: false, chats: [] };
    const isNumericId = /^\d+$/.test(String(userId));
    if (!isNumericId) return { success: true, chats: [] };

    const chatIds = specificChatId ? [specificChatId] : Array.from(this.knownChatIds);
    const affectedChats: (number | string)[] = [];

    for (const cId of chatIds) {
      try {
        const res = await fetch(`https://api.telegram.org/bot${this.token}/unbanChatMember`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: cId,
            user_id: Number(userId),
            only_if_banned: false,
          }),
        });
        const data = await res.json();
        if (data.ok) affectedChats.push(cId);
        else console.warn(`[Telegram API] unbanChatMember on chat ${cId} failed:`, data.description);
      } catch (err: any) {
        console.error(`[Telegram API] unbanChatMember error on chat ${cId}:`, err.message);
      }
    }
    return { success: affectedChats.length > 0, chats: affectedChats };
  }

  public async unmuteMember(
    userId: number | string,
    specificChatId?: number | string
  ): Promise<{ success: boolean; chats: (number | string)[] }> {
    if (!this.token) return { success: false, chats: [] };
    const isNumericId = /^\d+$/.test(String(userId));
    if (!isNumericId) return { success: true, chats: [] };

    const chatIds = specificChatId ? [specificChatId] : Array.from(this.knownChatIds);
    const affectedChats: (number | string)[] = [];

    for (const cId of chatIds) {
      try {
        const res = await fetch(`https://api.telegram.org/bot${this.token}/restrictChatMember`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: cId,
            user_id: Number(userId),
            permissions: {
              can_send_messages: true,
              can_send_audios: true,
              can_send_documents: true,
              can_send_photos: true,
              can_send_videos: true,
              can_send_video_notes: true,
              can_send_voice_notes: true,
              can_send_polls: true,
              can_send_other_messages: true,
              can_add_web_page_previews: true,
              can_change_info: false,
              can_invite_users: true,
              can_pin_messages: false,
            },
          }),
        });
        const data = await res.json();
        if (data.ok) affectedChats.push(cId);
        else console.warn(`[Telegram API] unmuteMember on chat ${cId} failed:`, data.description);
      } catch (err: any) {
        console.error(`[Telegram API] unmuteMember error on chat ${cId}:`, err.message);
      }
    }
    return { success: affectedChats.length > 0, chats: affectedChats };
  }

  public async unbanAndUnmuteMember(userId: number | string, specificChatId?: number | string) {
    const unbanRes = await this.unbanMember(userId, specificChatId);
    const unmuteRes = await this.unmuteMember(userId, specificChatId);
    const allChats = Array.from(new Set([...unbanRes.chats, ...unmuteRes.chats]));
    return {
      success: unbanRes.success || unmuteRes.success,
      unbannedChats: allChats,
    };
  }

  public async handleWebhookUpdate(update: any) {
    console.log('[Telegram Webhook] Received update ID:', update?.update_id);
    const msg = update?.message || update?.edited_message || update?.channel_post;
    if (!msg) {
      console.log('[Telegram Webhook] No message in update keys:', Object.keys(update || {}));
      return;
    }

    const text = (msg.text || msg.caption || '').trim();
    if (!text) {
      console.log('[Telegram Webhook] Message has no text or caption');
      return;
    }

    const chatId = msg.chat?.id;
    if (chatId) {
      this.knownChatIds.add(chatId);
    }

    const messageId = msg.message_id;
    const from = msg.from;
    if (!from) {
      console.log('[Telegram Webhook] Message has no sender (from)');
      return;
    }

    const userId = String(from.id);
    const username = from.username || from.first_name || `user_${userId}`;
    const fullName = [from.first_name, from.last_name].filter(Boolean).join(' ') || username;
    const avatarUrl = `https://api.dicebear.com/7.x/bottts/svg?seed=${userId}`;

    console.log(`[Telegram Webhook] Processing message from @${username} (${fullName}) in chat ${chatId}: "${text}"`);

    // Handle bot commands
    if (text.startsWith('/')) {
      const command = text.split(' ')[0].toLowerCase().split('@')[0];
      if (command === '/start' || command === '/help') {
        const helpText = `<b>🤖 Робот-модератор чата</b>
Я анализирую каждое сообщение в чате с помощью ИИ:
• Оценка качества сообщений от -5 до +5
• Фильтрация мата и оскорблений
• Определение эмоциональной тональности
• Подсчет персональной кармы участников
• Автоматический временный мут при накоплении отрицательного рейтинга (порог: ${store.getSettings().muteThreshold})

Команды:
/rating - проверить свой рейтинг
/stats - статистика модерации чата
/unban @username - разблокировать пользователя (для админов)
/unmute @username - снять мут с пользователя
/rules - правила чата`;
        await this.sendMessage(chatId, helpText, messageId);
        return;
      }

      if (command === '/rating' || command === '/karma') {
        const u = store.getUser(userId);
        const rating = u ? u.rating : 0;
        const status = u ? u.status : 'active';
        const ratingText = `👤 <b>Рейтинг @${username}</b>: ${rating > 0 ? '+' : ''}${rating}
📊 Всего сообщений: ${u ? u.totalMessages : 0}
Статус: ${status === 'muted' ? '🔇 Заблокирован' : status === 'banned' ? '🚫 Бан' : '✅ Активен'}`;
        await this.sendMessage(chatId, ratingText, messageId);
        return;
      }

      if (command === '/stats') {
        const stats = store.getStats();
        const statsMsg = `📊 <b>Статистика модерации чата</b>
• Проанализировано сообщений: ${stats.totalMessages}
• Нарушений пресечено: ${stats.totalViolations}
• Ненормативной лексики: ${stats.profanityCount}
• Пользователей в муте: ${stats.mutedUsersCount}
• Средний рейтинг участников: ${stats.averageRating}`;
        await this.sendMessage(chatId, statsMsg, messageId);
        return;
      }

      // In-chat admin unban/unmute commands
      if (command === '/unban' || command === '/unmute') {
        let targetUserId: string | null = null;
        let targetUsername: string | null = null;

        if (msg.reply_to_message?.from) {
          targetUserId = String(msg.reply_to_message.from.id);
          targetUsername = msg.reply_to_message.from.username || msg.reply_to_message.from.first_name || targetUserId;
        } else {
          const parts = text.split(/\s+/);
          if (parts.length > 1) {
            const query = parts[1].trim();
            const userFound = store.getUserByUsername(query) || store.getUser(query);
            if (userFound) {
              targetUserId = userFound.id;
              targetUsername = userFound.username;
            } else if (/^\d+$/.test(query)) {
              targetUserId = query;
              targetUsername = `user_${query}`;
            }
          }
        }

        if (!targetUserId) {
          await this.sendMessage(
            chatId,
            'ℹ️ Чтобы разблокировать пользователя, ответьте на его сообщение командой <code>/unban</code> или укажите логин: <code>/unban @username</code>',
            messageId
          );
          return;
        }

        // Lift restrictions in Telegram & restore rating in store
        store.updateUserStatus(targetUserId, 'active', undefined, true);
        await this.unbanAndUnmuteMember(targetUserId, chatId);

        const displayName = targetUsername ? '@' + targetUsername.replace(/^@/, '') : targetUserId;
        await this.sendMessage(
          chatId,
          `✅ <b>Пользователь ${displayName} успешно разблокирован!</b>\nВсе ограничения и мут сняты, карма сброшена до 0.`,
          messageId
        );
        return;
      }
    }

    // Call Gemini Moderation
    const userSummary = store.getUser(userId)
      ? `Текущий рейтинг: ${store.getUser(userId)!.rating}, нарушений: ${store.getUser(userId)!.toxicMessages}`
      : undefined;

    const modResult = await analyzeMessageWithGemini(text, userSummary);
    const result = store.processIncomingMessage(userId, username, fullName, text, modResult, avatarUrl, chatId);

    console.log(`[Telegram Webhook] Moderated message: ${modResult.score}/5, user rating: ${result.user.rating}`);

    const scoreSign = modResult.score > 0 ? '+' : '';
    const scoreEmoji =
      modResult.score >= 3
        ? '🌟'
        : modResult.score > 0
        ? '👍'
        : modResult.score === 0
        ? '💬'
        : modResult.score >= -2
        ? '⚠️'
        : '🚨';

    // Form score notification badge under message
    const scoreBadge = `${scoreEmoji} <b>[${scoreSign}${modResult.score}/5]</b> ${modResult.explanation} | Карма: ${result.user.rating}`;

    const settings = store.getSettings();
    const isNeutral = !modResult.profanityDetected && (modResult.sentiment === 'neutral' || modResult.score === 0);

    // If auto-delete profanity
    if (settings.autoDeleteProfanity && modResult.profanityDetected) {
      await this.deleteMessage(chatId, messageId);
    }

    // If auto-banned
    if (result.autoAction === 'banned') {
      await this.banMember(from.id, chatId);
      await this.sendMessage(
        chatId,
        `🚫 <b>Пользователь @${username} навсегда заблокирован в чате.</b>\nПричина: Кумулятивный рейтинг упал до критической отметки (${result.user.rating}).`
      );
    } else if (result.autoAction === 'muted') {
      // If auto-muted
      const untilUnix = Math.floor(Date.now() / 1000) + settings.muteDurationMinutes * 60;
      await this.restrictMember(chatId, from.id, untilUnix);
      await this.sendMessage(
        chatId,
        `🔇 <b>Пользователь @${username} временно заблокирован на ${settings.muteDurationMinutes} мин!</b>\nПричина: Высокий отрицательный рейтинг (${result.user.rating}).\nОценка: [${scoreSign}${modResult.score}/5] ${modResult.explanation}`
      );
    } else if (result.message.botReply) {
      // Send bot moderation reply (e.g. warning, mute, ban notice)
      await this.sendMessage(chatId, result.message.botReply, messageId);
    } else if (isNeutral) {
      // Нейтральные сообщения НЕ комментируются ботом
      if (settings.commentNeutralMessages) {
        await this.sendMessage(chatId, scoreBadge, messageId);
      }
    } else if (settings.showRatingBadgeUnderAll || modResult.score <= -2) {
      // Реакция на не-нейтральные сообщения с выраженным нарушением
      await this.sendMessage(chatId, scoreBadge, messageId);
    }
  }
}

export const telegramService = new TelegramService();
