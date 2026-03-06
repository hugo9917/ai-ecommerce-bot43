require('dotenv').config();

const qrcode = require('qrcode-terminal');
const { Client, LocalAuth } = require('whatsapp-web.js');
const { createClient } = require('@supabase/supabase-js');
const { GoogleGenerativeAI } = require('@google/generative-ai');

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_KEY;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

const supabase =
  SUPABASE_URL && SUPABASE_KEY ? createClient(SUPABASE_URL, SUPABASE_KEY) : null;

const genAI = GEMINI_API_KEY ? new GoogleGenerativeAI(GEMINI_API_KEY) : null;
const geminiModel = genAI
  ? genAI.getGenerativeModel({
      model: 'gemini-2.5-flash',
      systemInstruction:
        'Eres un asistente de compras. Extrae el precio máximo que el usuario quiere gastar. Devuelve ÚNICAMENTE un JSON válido con este formato exacto: {"precio_max": numero_entero_o_null}',
    })
  : null;

function isGroupMessage(message) {
  // En whatsapp-web.js los IDs de grupos terminan con @g.us
  return typeof message.from === 'string' && message.from.endsWith('@g.us');
}

function safeParseGeminiJson(text) {
  if (!text || typeof text !== 'string') return null;

  // A veces el modelo devuelve texto extra; intentamos extraer el primer objeto JSON.
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) return null;

  try {
    const obj = JSON.parse(match[0]);
    if (!obj || typeof obj !== 'object') return null;
    const precioMax = obj.precio_max;
    if (precioMax === null) return { precio_max: null };
    const n = Number(precioMax);
    if (!Number.isFinite(n)) return null;
    return { precio_max: Math.trunc(n) };
  } catch {
    return null;
  }
}

async function extractPrecioMax(userText) {
  if (!geminiModel) return { precio_max: null };

  const result = await geminiModel.generateContent(userText);
  const responseText = result?.response?.text?.() || '';
  const parsed = safeParseGeminiJson(responseText);
  return parsed || { precio_max: null };
}

function createWhatsAppClient() {
  return new Client({
    authStrategy: new LocalAuth({
      // Guarda la sesión en .wwebjs_auth/ por defecto.
      // clientId: 'bot-wpp', // Opcional si querés múltiples sesiones.
    }),
    puppeteer: {
      // En Windows suele ser más estable con sandbox desactivado.
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  });
}

async function main() {
  const client = createWhatsAppClient();

  client.on('qr', (qr) => {
    console.log('Escaneá este QR con WhatsApp para iniciar sesión:');
    qrcode.generate(qr, { small: true });
  });

  client.on('ready', () => {
    console.log('Bot conectado: listo para recibir mensajes.');
  });

  client.on('message', async (message) => {
    try {
      // Ignorar mensajes propios, estados y grupos.
      if (message.fromMe) return;
      if (message.from === 'status@broadcast') return;
      if (isGroupMessage(message)) return;

      const text = (message.body || '').trim();
      if (text === '!ping') {
        await message.reply(
          '¡Pong! El bot está conectado y leyendo tu base de datos (próximamente)'
        );
        return;
      }

      if (!supabase) {
        await message.reply(
          'Todavía no tengo configurada la conexión a la base de datos. Revisá SUPABASE_URL y SUPABASE_KEY en tu .env.'
        );
        return;
      }
      if (!geminiModel) {
        await message.reply(
          'Todavía no tengo configurada la IA. Revisá GEMINI_API_KEY en tu .env.'
        );
        return;
      }

      const { precio_max } = await extractPrecioMax(text);
      if (!precio_max || precio_max <= 0) {
        await message.reply(
          '¿Cuál es tu presupuesto máximo? Por ejemplo: "hasta $80000".'
        );
        return;
      }

      const { data, error } = await supabase
        .from('Camperas')
        .select('*')
        .lte('precio', precio_max)
        .order('precio', { ascending: true })
        .limit(3);

      if (error) {
        console.error('Error consultando Supabase:', error);
        await message.reply(
          'Tuve un problema consultando la base de datos. Probá de nuevo en un ratito.'
        );
        return;
      }

      if (!data || data.length === 0) {
        await message.reply(
          `No encontré camperas con precio menor o igual a $${precio_max}. Si querés, probá con un presupuesto más alto.`
        );
        return;
      }

      const lines = data.map((row, idx) => {
        const nombre = row.nombre ?? row.name ?? 'Sin nombre';
        const tienda = row.tienda ?? '—';
        const precio = row.precio ?? row.price ?? '—';
        const url = row.url_producto ?? row.product_url ?? '';
        return `${idx + 1}. ${nombre} (en ${tienda}) - $${precio}\n${url}`;
      });

      await message.reply(`¡Acá tenés algunas opciones!\n\n${lines.join('\n\n')}`);
    } catch (err) {
      console.error('Error manejando mensaje:', err);
      try {
        await message.reply(
          'Ocurrió un error procesando tu mensaje. Probá de nuevo en unos segundos.'
        );
      } catch {
        // ignorar error de reply
      }
    }
  });

  client.on('auth_failure', (msg) => {
    console.error('Fallo de autenticación:', msg);
  });

  client.on('disconnected', (reason) => {
    console.warn('Cliente desconectado:', reason);
  });

  process.on('unhandledRejection', (reason) => {
    console.error('Unhandled Promise Rejection:', reason);
  });

  process.on('uncaughtException', (err) => {
    console.error('Uncaught Exception:', err);
  });

  try {
    await client.initialize();
  } catch (err) {
    console.error('Error inicializando el cliente de WhatsApp:', err);
    process.exitCode = 1;
  }
}

main();

