# -*- coding: utf-8 -*-
import discord
from discord.ext import commands, tasks
import coc
from coc import errors as coc_errors
import asyncio
import os
import logging
import json
from datetime import datetime
import pytz
from dotenv import load_dotenv
# Importa a parte web do aiohttp para criar o servidor HTTP auxiliar
from aiohttp import web

# --- Carregar Variáveis de Ambiente ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
EMAIL = os.getenv('COC_EMAIL')
PASSWORD = os.getenv('COC_PASSWORD')
# Garante que a porta seja lida do ambiente ou use 8080 como padrão
PORT = int(os.getenv('PORT', 8080))


# --- Validação Inicial das Credenciais ---
if not TOKEN:
    print("ERRO CRÍTICO: DISCORD_TOKEN não encontrado no arquivo .env")
    exit()
if not EMAIL or not PASSWORD:
    print("ERRO CRÍTICO: COC_EMAIL ou COC_PASSWORD não encontrados no arquivo .env")
    exit()

# --- Configuração de Logging ---
log_formatter = logging.Formatter('%(asctime)s-%(levelname)s-[%(funcName)s]: %(message)s')
file_handler = logging.FileHandler("registro_bot.log", encoding='utf-8')
file_handler.setFormatter(log_formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
# Forçar handlers mesmo se root logger já tiver sido configurado por outra lib
logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler], force=True)
logger = logging.getLogger("registro-clash-bot")
logger.info("Logging configurado.")

# --- Constantes e Arquivos ---
CONFIG_FILE = "config.json"
REGISTRATIONS_FILE = "registrations.json"
PENDING_APPROVALS_FILE = "pending_approvals.json" # <-- Opcional, mas pode ser útil
COC_KEY_NAME = "clashlogsbot"
try:
    TIMEZONE = pytz.timezone('America/Sao_Paulo')
    logger.info(f"Timezone definida para {TIMEZONE}")
except pytz.UnknownTimeZoneError:
    logger.error("Timezone 'America/Sao_Paulo' não encontrada. Usando UTC.")
    TIMEZONE = pytz.utc

# --- Variáveis Globais ---
config = {}
registrations = {}
# pending_approvals = {} # <-- Opcional, descomente se usar PENDING_APPROVALS_FILE
coc_client = None

# --- Funções Utilitárias para JSON ---
def load_json(filename):
    """Carrega dados de um arquivo JSON."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Erro ao carregar {filename}: {e}")
            return {}
    logger.warning(f"Arquivo {filename} não encontrado, iniciando com dados vazios.")
    return {}

def save_json(data, filename):
    """Salva dados em um arquivo JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.debug(f"Dados salvos em {filename}")
        return True
    except IOError as e:
        logger.error(f"Erro ao salvar {filename}: {e}")
        return False

# --- Inicialização do Cliente CoC ---
async def initialize_coc_client():
    """Tenta logar no CoC API usando Email/Senha e encontrar/usar a chave especificada."""
    # Declaração global no início
    global coc_client
    logger.info("--- Iniciando Login Cliente CoC ---")
    for attempt in range(1, 4):
        try:
            logger.info(f"[Tentativa {attempt}/3] Criando Client CoC para procurar/usar a chave chamada '{COC_KEY_NAME}'...")
            temp_client = coc.Client(key_count=1, key_names=COC_KEY_NAME, throttle_limit=20)
            logger.info(f"[Tentativa {attempt}/3] Tentando login com Email/Senha...")
            await asyncio.wait_for(temp_client.login(EMAIL, PASSWORD), timeout=90.0)
            if hasattr(temp_client, 'http') and temp_client.http:
                 # Atribui à variável global
                 coc_client = temp_client
                 logger.info(f"[Tentativa {attempt}/3] Login CoC e inicialização do Client OK. O bot tentará usar a chave '{COC_KEY_NAME}' se encontrada.")
                 return True
            else:
                 logger.error(f"[Tentativa {attempt}/3] Login CoC pareceu OK, mas a sessão HTTP não foi estabelecida corretamente.")
                 try:
                     await temp_client.close()
                 except Exception:
                     pass
        except coc_errors.AuthenticationError as e_auth:
            logger.error(f"[Tentativa {attempt}/3] Falha de autenticação CoC: {e_auth}. Verifique email/senha e 2FA se aplicável.")
            return False
        except asyncio.TimeoutError:
            logger.error(f"[Tentativa {attempt}/3] Timeout durante o processo de login CoC.")
        except Exception as e_login:
            logger.error(f"[Tentativa {attempt}/3] Erro inesperado durante login/inicialização do Client CoC: {e_login}", exc_info=True)
            if 'temp_client' in locals() and temp_client:
                try:
                    await temp_client.close()
                except Exception:
                    pass
        if attempt < 3:
            wait_time = 20 * attempt
            logger.info(f"Aguardando {wait_time}s antes da próxima tentativa...")
            await asyncio.sleep(wait_time)
    logger.critical("--- Falha em todas as tentativas de login CoC ---")
    # Garante que a global seja None se falhar
    coc_client = None
    return False

# --- Bot Discord ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# --- Evento On Ready ---
@bot.event
async def on_ready():
    """Executado quando o bot está online e pronto."""
    # Declaração global no início
    global config, registrations, coc_client #, pending_approvals # Opcional
    logger.info(f"Bot {bot.user.name} ({bot.user.id}) conectado ao Discord!")
    logger.info(f"Usando discord.py v{discord.__version__}")
    logger.info(f"Executando em {len(bot.guilds)} servidor(es).")
    if bot.guilds:
        logger.info(f"Servidor exemplo: {bot.guilds[0].name} ({bot.guilds[0].id})")
    else:
        logger.warning("Bot não parece estar em nenhum servidor!")

    # Lê as configurações e registros
    config = load_json(CONFIG_FILE)
    registrations = load_json(REGISTRATIONS_FILE)
    # pending_approvals = load_json(PENDING_APPROVALS_FILE) # Opcional
    logger.info(f"Configurações carregadas ({len(config)} itens).")
    logger.info(f"Registros carregados ({len(registrations)} usuários).")
    # logger.info(f"Aprovações pendentes carregadas ({len(pending_approvals)}).") # Opcional

    try:
        synced = await bot.tree.sync()
        logger.info(f"Sincronizados {len(synced)} comandos slash.")
    except Exception as e:
        logger.error(f"Falha ao sincronizar comandos slash: {e}")

    # Inicializa o cliente CoC (que usa a global coc_client)
    if not await initialize_coc_client():
        logger.critical("Falha ao inicializar cliente CoC. Funcionalidade de verificação/registro estará DESABILITADA.")
    else:
        logger.info("Cliente CoC inicializado com sucesso.")
        # Inicia a tarefa APENAS se o cliente CoC funcionou E se não estiver rodando
        if not verify_members_task.is_running():
            verify_members_task.start()
            logger.info("Tarefa de verificação periódica iniciada.")
        else:
             logger.warning("Tarefa de verificação periódica já estava rodando.")

    logger.info("Bot pronto!")


# --- Comando /setup ---
@bot.tree.command(name="setup", description="Configura o bot de registro (apenas Admins).")
@discord.app_commands.describe(
    clan_tag="A tag do seu clã no Clash of Clans (ex: #ABCDEF).",
    registration_channel="Canal onde os membros usarão /registrar.",
    log_channel="Canal para logs gerais do bot (aprovações, negações, expulsões).",
    approval_log_channel="Canal ONDE AS SOLICITAÇÕES de registro ficam PENDENTES para admins.",
    member_role="Cargo para Membros do clã.",
    elder_role="Cargo para Anciãos do clã.",
    coleader_role="Cargo para Co-Líderes do clã.",
    kick_message="Mensagem a ser enviada ao membro ao ser expulso (opcional)."
)
async def setup_command(
    interaction: discord.Interaction,
    clan_tag: str,
    registration_channel: discord.TextChannel,
    log_channel: discord.TextChannel,
    approval_log_channel: discord.TextChannel,
    member_role: discord.Role,
    elder_role: discord.Role,
    coleader_role: discord.Role,
    kick_message: str = "Você foi removido do servidor por não fazer mais parte do clã."
):
    """Comando para configurar as definições essenciais do bot."""
    # Declaração global no início
    global config
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("❌ Você precisa ser um administrador para usar este comando.", ephemeral=True)
        return

    try:
        corrected_clan_tag = coc.utils.correct_tag(clan_tag)
        if not coc.utils.is_valid_tag(corrected_clan_tag):
            await interaction.followup.send("❌ A tag do clã fornecida é inválida. Use o formato #TAG.", ephemeral=True)
            return
    except Exception as e:
         logger.error(f"Erro ao validar tag do clã {clan_tag}: {e}")
         await interaction.followup.send("❌ Erro ao processar a tag do clã.", ephemeral=True)
         return

    bot_member = interaction.guild.me
    channels_to_check = {
        "Registro": registration_channel,
        "Logs": log_channel,
        "Aprovações": approval_log_channel
    }
    missing_perms = []
    for name, channel in channels_to_check.items():
        perms = channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.view_channel:
             missing_perms.append(f"Enviar mensagens em {channel.mention} (Canal de {name})")

    if missing_perms:
         perm_list = "\n - ".join(missing_perms)
         await interaction.followup.send(f"❌ Não tenho as permissões necessárias:\n - {perm_list}\nVerifique minhas permissões nesses canais.", ephemeral=True)
         return

    if not bot_member:
         await interaction.followup.send("❌ Não consegui encontrar minhas próprias informações neste servidor.", ephemeral=True)
         return
    roles_to_manage = [member_role, elder_role, coleader_role]
    failed_hierarchy = []
    for role in roles_to_manage:
        if bot_member.top_role <= role:
            failed_hierarchy.append(f"`{role.name}`")

    if failed_hierarchy:
        role_list = ", ".join(failed_hierarchy)
        await interaction.followup.send(f"❌ Meu cargo (`{bot_member.top_role.name}`) é igual ou inferior a um dos cargos que preciso gerenciar ({role_list}). Por favor, mova meu cargo para cima na lista de cargos do servidor.", ephemeral=True)
        return

    new_config = {
        "clan_tag": corrected_clan_tag,
        "registration_channel_id": registration_channel.id,
        "log_channel_id": log_channel.id,
        "approval_log_channel_id": approval_log_channel.id,
        "roles": {
            "member": member_role.id,
            "admin": elder_role.id,
            "elder": elder_role.id,
            "coleader": coleader_role.id,
            "leader": coleader_role.id
        },
        "kick_message": kick_message or "Você foi removido do servidor por não fazer mais parte do clã."
    }

    if save_json(new_config, CONFIG_FILE):
        # Atualiza a global config
        config = new_config
        logger.info(f"Configuração salva/atualizada por {interaction.user} ({interaction.user.id}). Clã: {config['clan_tag']}")
        confirmation_message = (
            f"✅ Configuração salva com sucesso!\n"
            f" - **Clã:** `{config['clan_tag']}`\n"
            f" - **Canal Registro:** {registration_channel.mention}\n"
            f" - **Canal Logs Gerais:** {log_channel.mention}\n"
            f" - **Canal Aprovações:** {approval_log_channel.mention}\n"
            f" - **Cargo Membro:** {member_role.mention}\n"
            f" - **Cargo Ancião:** {elder_role.mention} (Usado para 'admin' e 'elder' do CoC)\n"
            f" - **Cargo Colíder:** {coleader_role.mention} (Usado para 'coLeader' e 'leader' do CoC)\n"
            f" - **Msg Expulsão:** {'`' + config['kick_message'] + '`' if config['kick_message'] else '*(Padrão)*'}"
        )
        await interaction.followup.send(confirmation_message, ephemeral=True)

        log_ch_obj = bot.get_channel(config.get("log_channel_id"))
        if log_ch_obj:
            try:
                approval_ch_obj = bot.get_channel(config.get('approval_log_channel_id'))
                approval_mention = approval_ch_obj.mention if approval_ch_obj else f"ID {config.get('approval_log_channel_id')}"
                await log_ch_obj.send(f"ℹ️ Bot configurado/atualizado por {interaction.user.mention}. Registros em {registration_channel.mention}, Aprovações em {approval_mention}.")
            except Exception as e:
                logger.error(f"Falha ao enviar mensagem de confirmação setup para canal de log: {e}")
    else:
        await interaction.followup.send("❌ Falha grave ao salvar o arquivo de configuração no disco.", ephemeral=True)


# --- Comando /registrar ---
@bot.tree.command(name="registrar", description="Solicita o registro no clã com sua tag do Clash of Clans.")
@discord.app_commands.describe(player_tag="Sua tag de jogador no Clash of Clans (ex: #XYZABCD).")
async def register_command(
    interaction: discord.Interaction,
    player_tag: str
):
    """Solicita o registro de um membro para aprovação administrativa."""
    # Declaração global no início
    global coc_client
    await interaction.response.defer(ephemeral=True)

    if not config or "clan_tag" not in config or not config.get("roles") or not config.get("approval_log_channel_id"):
        await interaction.followup.send("❌ O bot ainda não foi completamente configurado (falta definir clã, cargos ou canal de aprovação). Peça a um admin para usar `/setup`.", ephemeral=True)
        return
    # Usa a global coc_client (declarada acima)
    if not coc_client or not hasattr(coc_client, 'http') or not coc_client.http:
        await interaction.followup.send("⏳ A conexão com o Clash of Clans ainda está sendo estabelecida ou falhou. Tente novamente em um minuto ou contate um admin.", ephemeral=True)
        return

    reg_channel_id = config.get("registration_channel_id")
    if not reg_channel_id or interaction.channel.id != reg_channel_id:
        reg_channel = bot.get_channel(reg_channel_id) if reg_channel_id else None
        mention = f"no canal {reg_channel.mention}" if reg_channel else "no canal de registro designado"
        await interaction.followup.send(f"❌ Use este comando {mention}.", ephemeral=True)
        return

    try:
        corrected_tag = coc.utils.correct_tag(player_tag)
        if not coc.utils.is_valid_tag(corrected_tag):
            await interaction.followup.send(f"❌ A tag `{player_tag}` parece inválida. Use o formato #TAG.", ephemeral=True)
            return
    except Exception as e:
         logger.error(f"Erro ao validar tag do jogador {player_tag}: {e}")
         await interaction.followup.send("❌ Erro ao processar a tag do jogador.", ephemeral=True)
         return

    discord_id_str = str(interaction.user.id)
    if discord_id_str in registrations:
        if registrations[discord_id_str] == corrected_tag:
             await interaction.followup.send(f"ℹ️ Você já está registrado com a tag `{corrected_tag}`.", ephemeral=True)
             await verify_single_member(interaction.user, corrected_tag, interaction.guild)
             return
        else:
             logger.warning(f"Usuário {interaction.user} ({discord_id_str}), já registrado com {registrations[discord_id_str]}, tentando registrar nova tag {corrected_tag}.")

    tag_already_registered_by_other = False
    other_user_id = None
    for reg_id, reg_tag in registrations.items():
        if reg_tag == corrected_tag and reg_id != discord_id_str:
            tag_already_registered_by_other = True
            other_user_id = reg_id
            break

    if tag_already_registered_by_other:
        other_user = interaction.guild.get_member(int(other_user_id))
        other_user_mention = f"<@{other_user_id}>" if not other_user else other_user.mention
        logger.warning(f"Tentativa de registro da tag {corrected_tag} por {interaction.user}, mas já registrada para {other_user_mention} ({other_user_id}).")
        await interaction.followup.send(f"❌ A tag `{corrected_tag}` já está registrada por outro usuário ({other_user_mention}). Se isso for um erro, contate um administrador.", ephemeral=True)
        return

    log_channel = bot.get_channel(config.get("log_channel_id")) if config.get("log_channel_id") else None
    approval_log_channel_id = config.get("approval_log_channel_id")
    approval_log_channel = bot.get_channel(approval_log_channel_id)
    if not approval_log_channel:
         logger.error(f"Canal de aprovação configurado (ID: {approval_log_channel_id}) não encontrado.")
         await interaction.followup.send("❌ Erro crítico: O canal configurado para aprovações não foi encontrado. Contate um admin.", ephemeral=True)
         if log_channel:
             try: await log_channel.send(f"🆘 **Erro Crítico:** Canal de aprovação ID `{approval_log_channel_id}` não encontrado ao processar registro de {interaction.user.mention}.")
             except Exception: pass
         return

    try:
        logger.info(f"Usuário {interaction.user} ({interaction.user.id}) solicitando registro com tag {corrected_tag}")
        # Usa a global coc_client (declarada no início da função)
        clan = await asyncio.wait_for(coc_client.get_clan(config["clan_tag"]), timeout=30.0)
        member_data = clan.get_member(corrected_tag)

        if member_data:
            player_name = member_data.name
            player_role_coc = member_data.role.in_game_name
            logger.info(f"Tag {corrected_tag} encontrada no clã {clan.name}. Jogador: {player_name}, Cargo CoC: {player_role_coc}")

            role_name_display = player_role_coc.replace("coLeader", "Co-Líder").capitalize()

            approval_message = (
                f"📝 **Solicitação de Registro Pendente**\n\n"
                f"👤 **Usuário Discord:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"🏷️ **Tag CoC:** `{corrected_tag}`\n"
                f"🔖 **Nome no Jogo:** `{player_name}`\n"
                f"👑 **Cargo no Clã:** {role_name_display}\n\n"
                f"▶️ **Para aprovar:** Use `/aprovar usuario: {interaction.user.mention} player_tag: {corrected_tag}`\n"
                f"❌ **Para negar:** Use `/negar usuario: {interaction.user.mention} player_tag: {corrected_tag} motivo: [Opcional]`"
            )
            try:
                await approval_log_channel.send(approval_message)
                logger.info(f"Solicitação de registro para {interaction.user} ({corrected_tag}) enviada para o canal {approval_log_channel.name}")
                await interaction.followup.send(f"✅ Sua solicitação de registro para a tag `{corrected_tag}` (`{player_name}`) foi enviada para aprovação administrativa. Você será notificado se for aprovado ou negado.", ephemeral=True)

            except discord.Forbidden:
                logger.error(f"Sem permissão para enviar mensagem no canal de aprovação {approval_log_channel.mention}")
                await interaction.followup.send(f"❌ Erro ao enviar sua solicitação para o canal {approval_log_channel.mention}. Verifique as permissões do bot ou contate um admin.", ephemeral=True)
            except Exception as e:
                logger.error(f"Erro ao enviar para canal de aprovação: {e}", exc_info=True)
                await interaction.followup.send("❌ Ocorreu um erro interno ao enviar sua solicitação para aprovação.", ephemeral=True)

        else:
            logger.info(f"Tag {corrected_tag} NÃO encontrada no clã {clan.name} ({config['clan_tag']}) para {interaction.user}.")
            await interaction.followup.send(f"❌ Jogador com a tag `{corrected_tag}` não encontrado no clã **{clan.name}** (`{config['clan_tag']}`).\nVerifique se a tag está correta e se você realmente faz parte deste clã.", ephemeral=True)
            if log_channel:
                 try:
                    await log_channel.send(f"⚠️ Falha na solicitação de registro de {interaction.user.mention}: Tag `{corrected_tag}` não encontrada no clã `{config['clan_tag']}`.")
                 except Exception as e:
                     logger.error(f"Falha ao enviar log de registro (não encontrado) para canal: {e}")

    except coc_errors.NotFound:
        logger.error(f"Clã {config.get('clan_tag', 'N/A')} não encontrado pela API CoC durante solicitação de registro.")
        await interaction.followup.send(f"❌ Erro: Não consegui encontrar o clã `{config.get('clan_tag', 'N/A')}` configurado no bot. Peça a um admin para verificar a tag no `/setup`.", ephemeral=True)
    except coc_errors.AuthenticationError:
        logger.critical("Erro de autenticação CoC durante comando /registrar. Tentando relogar...")
        # Usa a global coc_client (declarada no início da função)
        coc_client = None
        await initialize_coc_client() # Tenta reinicializar o cliente global
        await interaction.followup.send("❌ Ocorreu um problema temporário de conexão com a API do Clash of Clans. Por favor, tente registrar novamente em um instante.", ephemeral=True)
    except coc_errors.ClashOfClansException as e_coc:
        logger.error(f"Erro da API CoC ({type(e_coc).__name__}) ao solicitar registro {corrected_tag}: {e_coc}")
        await interaction.followup.send(f"❌ Ocorreu um erro ao comunicar com a API do Clash of Clans ({type(e_coc).__name__}). Tente novamente mais tarde.", ephemeral=True)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ao buscar clã/jogador ({corrected_tag}) para solicitação de registro.")
        await interaction.followup.send("❌ A API do Clash of Clans demorou muito para responder. Tente novamente.", ephemeral=True)
    except Exception as e:
        logger.error(f"Erro inesperado no comando /registrar para {corrected_tag}: {e}", exc_info=True)
        await interaction.followup.send("❌ Ocorreu um erro inesperado durante a solicitação. Contate um admin.", ephemeral=True)

# --- Comando /aprovar ---
@bot.tree.command(name="aprovar", description="[Admin] Aprova o registro de um usuário.")
@discord.app_commands.describe(
    usuario="O membro do Discord que solicitou o registro.",
    player_tag="A tag CoC que o membro informou e que está sendo aprovada."
)
async def aprovar_command(interaction: discord.Interaction, usuario: discord.Member, player_tag: str):
    """Aprova um registro pendente, verifica novamente o cargo e atribui."""
    # Declaração global no início
    global coc_client
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    if not config or "clan_tag" not in config or not config.get("roles"):
        await interaction.followup.send("❌ O bot não está configurado. Use `/setup`.", ephemeral=True)
        return
    # Usa a global coc_client (declarada acima)
    if not coc_client or not hasattr(coc_client, 'http') or not coc_client.http:
        await interaction.followup.send("❌ Cliente CoC não está pronto ou desconectado. Tente novamente em breve.", ephemeral=True)
        return

    log_channel = bot.get_channel(config.get("log_channel_id")) if config.get("log_channel_id") else None

    try:
        corrected_tag = coc.utils.correct_tag(player_tag)
        if not coc.utils.is_valid_tag(corrected_tag):
            await interaction.followup.send(f"❌ A tag `{player_tag}` parece inválida.", ephemeral=True)
            return
    except Exception as e:
         logger.error(f"Erro ao validar tag {player_tag} em /aprovar: {e}")
         await interaction.followup.send("❌ Erro ao processar a tag CoC.", ephemeral=True)
         return

    discord_id_str = str(usuario.id)
    overwriting_user = None
    for reg_id, reg_tag in registrations.items():
        if reg_tag == corrected_tag and reg_id != discord_id_str:
            other_user = interaction.guild.get_member(int(reg_id))
            other_user_mention = f"<@{reg_id}>" if not other_user else other_user.mention
            logger.warning(f"Admin {interaction.user} tentando aprovar {usuario} para tag {corrected_tag}, mas já registrada para {other_user_mention} ({reg_id}). O registro anterior será sobrescrito.")
            overwriting_user = other_user_mention
            break

    try:
        logger.info(f"[APROVAÇÃO] Admin {interaction.user} aprovando {usuario} ({discord_id_str}) para tag {corrected_tag}")
        # Usa a global coc_client (declarada no início da função)
        clan = await asyncio.wait_for(coc_client.get_clan(config["clan_tag"]), timeout=30.0)
        member_data = clan.get_member(corrected_tag)

        if not member_data:
            logger.warning(f"[APROVAÇÃO] Tag {corrected_tag} NÃO encontrada no clã {clan.name} no momento da aprovação para {usuario}.")
            await interaction.followup.send(f"❌ Falha na aprovação: Jogador com tag `{corrected_tag}` **não encontrado no clã neste momento**. Peça ao usuário para registrar novamente se ele retornou ao clã.", ephemeral=True)
            if log_channel:
                 try: await log_channel.send(f"❌ Falha na aprovação por {interaction.user.mention}: {usuario.mention} (tag `{corrected_tag}`) não encontrado no clã `{config['clan_tag']}` no momento da tentativa.")
                 except Exception: pass
            return

        player_name = member_data.name
        player_role_coc = member_data.role.in_game_name.lower()
        role_id_to_assign = config.get("roles", {}).get(player_role_coc)

        if not role_id_to_assign:
            logger.error(f"[APROVAÇÃO] Cargo CoC '{player_role_coc}' (tag: {corrected_tag}) não tem mapeamento em config.json['roles'].")
            await interaction.followup.send(f"❌ Falha na aprovação: O cargo CoC '{player_role_coc}' do jogador não tem um cargo Discord correspondente configurado no bot. Use `/setup` para verificar os mapeamentos de cargos.", ephemeral=True)
            if log_channel:
                 try: await log_channel.send(f"⚠️ Falha na aprovação por {interaction.user.mention}: Mapeamento de cargo CoC '{player_role_coc}' para Discord ausente na configuração (jogador {usuario.mention}, tag `{corrected_tag}`).")
                 except Exception: pass
            return

        role_to_assign = interaction.guild.get_role(role_id_to_assign)
        if not role_to_assign:
            logger.error(f"[APROVAÇÃO] Cargo Discord ID {role_id_to_assign} (mapeado de '{player_role_coc}') não encontrado no servidor.")
            await interaction.followup.send(f"❌ Falha na aprovação: O cargo Discord configurado (ID: {role_id_to_assign}) para o cargo CoC '{player_role_coc}' não foi encontrado neste servidor.", ephemeral=True)
            if log_channel:
                 try: await log_channel.send(f"🆘 Erro na aprovação por {interaction.user.mention}: Cargo Discord ID `{role_id_to_assign}` não encontrado no servidor (para {usuario.mention}, tag `{corrected_tag}`).")
                 except Exception: pass
            return

        bot_member = interaction.guild.me
        if bot_member.top_role <= role_to_assign:
             logger.warning(f"[APROVAÇÃO] Hierarquia Inválida: Bot (Top: {bot_member.top_role.name}) não pode dar o cargo {role_to_assign.name}.")
             await interaction.followup.send(f"❌ Falha na aprovação: Não posso atribuir o cargo {role_to_assign.mention} porque meu cargo mais alto (`{bot_member.top_role.name}`) não está acima dele na lista de cargos do servidor.", ephemeral=True)
             return

        try:
            all_managed_role_ids = [r_id for r_id in config.get("roles", {}).values() if r_id]
            roles_to_remove = [r for r in usuario.roles if r.id in all_managed_role_ids and r.id != role_to_assign.id]

            if roles_to_remove:
                await usuario.remove_roles(*roles_to_remove, reason=f"Remoção de cargos antigos antes da aprovação ({corrected_tag}) por {interaction.user}")
                logger.debug(f"Removidos cargos antigos de {usuario} antes da aprovação: {[r.name for r in roles_to_remove]}")
                await asyncio.sleep(0.5)

            if role_to_assign not in usuario.roles:
                await usuario.add_roles(role_to_assign, reason=f"Registro aprovado por {interaction.user} - Tag: {corrected_tag}")
                logger.info(f"[APROVAÇÃO] Cargo {role_to_assign.name} adicionado para {usuario} ({discord_id_str}).")
            else:
                 logger.info(f"[APROVAÇÃO] Usuário {usuario} já possuía o cargo {role_to_assign.name}. Apenas registrando.")

            registrations[discord_id_str] = corrected_tag
            if save_json(registrations, REGISTRATIONS_FILE):
                logger.info(f"[APROVAÇÃO] Registro salvo: Discord ID {discord_id_str} -> CoC Tag {corrected_tag}")

                success_message = f"✅ Registro de {usuario.mention} para a tag `{corrected_tag}` (`{player_name}`) como **{role_to_assign.name}** aprovado com sucesso!"
                if overwriting_user:
                    success_message += f"\n⚠️ **Aviso:** Esta tag estava anteriormente registrada para {overwriting_user}. O registro foi sobrescrito."
                await interaction.followup.send(success_message, ephemeral=True)

                if log_channel:
                    log_msg = f"✅ **{interaction.user.mention}** aprovou o registro de **{usuario.mention}** (`{discord_id_str}`) com a tag `{corrected_tag}` como **{player_role_coc.capitalize()}** ({role_to_assign.mention})."
                    if overwriting_user:
                        log_msg += f" (Sobrescreveu registro anterior de {overwriting_user})"
                    try: await log_channel.send(log_msg)
                    except Exception: pass

                try:
                    await usuario.send(f"🎉 Seu registro no servidor **{interaction.guild.name}** foi aprovado! Você recebeu o cargo **{role_to_assign.name}** por ter a tag `{corrected_tag}` (`{player_name}`).")
                except discord.Forbidden:
                    logger.warning(f"Não foi possível enviar DM de aprovação para {usuario} (DMs desativadas?).")
                except Exception as e_dm:
                    logger.error(f"Erro ao enviar DM de aprovação para {usuario}: {e_dm}")

            else:
                 logger.critical(f"[APROVAÇÃO] FALHA AO SALVAR registro para {discord_id_str} -> {corrected_tag} após aprovação!")
                 await interaction.followup.send("❌ Erro crítico ao salvar o registro no arquivo após a aprovação. O cargo foi dado, mas o registro pode não ter sido salvo permanentemente.", ephemeral=True)
                 if log_channel:
                     try: await log_channel.send(f"🆘 **ERRO CRÍTICO:** Falha ao salvar {REGISTRATIONS_FILE} após aprovar {usuario.mention} (`{corrected_tag}`). O cargo foi dado, mas o registro não foi salvo!")
                     except Exception: pass

        except discord.Forbidden:
            logger.error(f"[APROVAÇÃO] Sem permissão para gerenciar cargo {role_to_assign.name} para {usuario}.")
            await interaction.followup.send(f"❌ Erro de Permissão: Não tenho permissão para adicionar/remover o cargo '{role_to_assign.name}'. Verifique a hierarquia de cargos e minhas permissões.", ephemeral=True)
        except Exception as e_role:
            logger.error(f"[APROVAÇÃO] Erro ao adicionar/remover cargo para {usuario}: {e_role}", exc_info=True)
            await interaction.followup.send("❌ Ocorreu um erro interno ao tentar atribuir o cargo.", ephemeral=True)

    except coc_errors.NotFound:
        logger.error(f"[APROVAÇÃO] Clã {config['clan_tag']} não encontrado pela API ao aprovar {corrected_tag}.")
        await interaction.followup.send(f"❌ Erro: Clã `{config['clan_tag']}` não encontrado na API CoC ao tentar aprovar.", ephemeral=True)
    except coc_errors.AuthenticationError:
        logger.critical("[APROVAÇÃO] Erro de autenticação CoC ao aprovar.")
        # <<< CORREÇÃO: Remover a declaração global redundante daqui >>>
        # A variável coc_client já é global devido à declaração no início da função.
        coc_client = None
        await initialize_coc_client() # Tenta reinicializar o cliente global
        await interaction.followup.send("❌ Erro crítico de conexão com a API do Clash of Clans ao tentar aprovar. Tente novamente em instantes.", ephemeral=True)
    except coc_errors.ClashOfClansException as e_coc:
        logger.error(f"[APROVAÇÃO] Erro API CoC ({type(e_coc).__name__}) ao buscar {corrected_tag} para aprovação: {e_coc}")
        await interaction.followup.send(f"❌ Erro ao comunicar com a API CoC ({type(e_coc).__name__}) durante a aprovação. Tente novamente.", ephemeral=True)
    except asyncio.TimeoutError:
        logger.warning(f"[APROVAÇÃO] Timeout ao buscar dados de {corrected_tag} para aprovação.")
        await interaction.followup.send("❌ API CoC demorou muito para responder durante a aprovação.", ephemeral=True)
    except Exception as e:
        logger.error(f"[APROVAÇÃO] Erro inesperado para {corrected_tag} / {usuario}: {e}", exc_info=True)
        await interaction.followup.send("❌ Ocorreu um erro inesperado durante a aprovação.", ephemeral=True)

# --- Comando /negar ---
@bot.tree.command(name="negar", description="[Admin] Nega uma solicitação de registro pendente.")
@discord.app_commands.describe(
    usuario="O membro do Discord que solicitou o registro.",
    player_tag="A tag CoC informada na solicitação que está sendo negada.",
    motivo="O motivo da negação (será enviado ao usuário se possível)."
)
async def negar_command(interaction: discord.Interaction, usuario: discord.Member, player_tag: str, motivo: str = None):
    """Nega uma solicitação de registro e loga a ação."""
    # Nenhuma global necessária aqui, apenas lê config
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    log_channel_id = config.get("log_channel_id")
    log_channel = bot.get_channel(log_channel_id) if log_channel_id else None

    try:
        corrected_tag = coc.utils.correct_tag(player_tag)
    except:
        corrected_tag = player_tag

    logger.info(f"[NEGAÇÃO] Admin {interaction.user} negando registro de {usuario} ({usuario.id}) para tag {corrected_tag}. Motivo: {motivo or 'Não especificado'}")

    await interaction.followup.send(f"✅ Solicitação de registro de {usuario.mention} para a tag `{corrected_tag}` negada.", ephemeral=True)

    if log_channel:
        log_message = f"❌ **{interaction.user.mention}** negou a solicitação de registro de **{usuario.mention}** (`{usuario.id}`) para a tag `{corrected_tag}`."
        if motivo:
            log_message += f"\n> Motivo: {motivo}"
        try:
            await log_channel.send(log_message)
        except Exception as e:
            logger.error(f"Falha ao enviar log de negação para canal: {e}")

    dm_message = f"ℹ️ Sua solicitação de registro no servidor **{interaction.guild.name}** para a tag `{corrected_tag}` foi negada por um administrador."
    if motivo:
        dm_message += f"\n\n**Motivo:** {motivo}"

    try:
        await usuario.send(dm_message)
    except discord.Forbidden:
        logger.warning(f"Não foi possível enviar DM de negação para {usuario} (DMs desativadas?).")
    except Exception as e_dm:
        logger.error(f"Erro ao enviar DM de negação para {usuario}: {e_dm}")

# --- Função auxiliar para verificar e atualizar um único membro ---
async def verify_single_member(member: discord.Member, expected_tag: str, guild: discord.Guild):
    """Verifica o status CoC de um membro específico e atualiza cargos/expulsa se necessário."""
    # Declaração global no início da função
    global coc_client
    global registrations

    # Usa as globais (declaradas acima)
    if not coc_client or not config or not guild:
        logger.debug(f"Skipping single verify for {member}: coc_client ou config indisponível.")
        return

    discord_id_str = str(member.id)
    logger.debug(f"Verificando membro individual: {member} ({discord_id_str}), tag esperada: {expected_tag}")

    try:
        # Usa a global coc_client
        clan = await asyncio.wait_for(coc_client.get_clan(config["clan_tag"]), timeout=20.0)
        member_data = clan.get_member(expected_tag)

        current_roles = {role.id for role in member.roles}
        all_managed_role_ids = set(config.get("roles", {}).values())
        current_managed_roles = current_roles.intersection(all_managed_role_ids)

        if member_data:
            # Membro ENCONTRADO no clã
            player_role_coc = member_data.role.in_game_name.lower()
            expected_role_id = config.get("roles", {}).get(player_role_coc)
            expected_role = guild.get_role(expected_role_id) if expected_role_id else None

            if not expected_role:
                logger.error(f"Cargo Discord para CoC role '{player_role_coc}' (ID: {expected_role_id}) não encontrado ou não configurado para {member}.")
                return

            if expected_role_id not in current_roles:
                logger.info(f"Membro {member} ({expected_tag}) está no clã como {player_role_coc}, mas sem o cargo {expected_role.name}. Adicionando...")
                roles_to_remove = [guild.get_role(rid) for rid in current_managed_roles if rid != expected_role_id]
                roles_to_remove = [r for r in roles_to_remove if r]
                if roles_to_remove:
                     await member.remove_roles(*roles_to_remove, reason=f"Correção de cargo - Verificação periódica/aprovação")
                if guild.me.top_role > expected_role:
                     await member.add_roles(expected_role, reason=f"Cargo correto ({player_role_coc}) - Verificação periódica/aprovação")
                else:
                     logger.warning(f"Não foi possível adicionar cargo {expected_role.name} a {member} - Hierarquia insuficiente.")

            incorrect_managed_roles = current_managed_roles - {expected_role_id}
            if incorrect_managed_roles:
                 roles_to_remove = [guild.get_role(rid) for rid in incorrect_managed_roles]
                 roles_to_remove = [r for r in roles_to_remove if r]
                 if roles_to_remove:
                     logger.info(f"Membro {member} ({expected_tag}) tem cargos incorretos ({[r.name for r in roles_to_remove]}). Removendo...")
                     await member.remove_roles(*roles_to_remove, reason="Correção de cargo - Verificação periódica")

        else:
            # Membro NÃO ENCONTRADO no clã com a tag registrada
            logger.info(f"Membro {member} ({expected_tag}) não encontrado no clã {config['clan_tag']}. Removendo cargos/expulsando...")

            roles_to_remove = [guild.get_role(rid) for rid in current_managed_roles]
            roles_to_remove = [r for r in roles_to_remove if r]
            if roles_to_remove:
                 await member.remove_roles(*roles_to_remove, reason="Não está mais no clã - Verificação")

            # Usa a global registrations (declarada no início da função)
            if discord_id_str in registrations:
                 del registrations[discord_id_str]
                 save_json(registrations, REGISTRATIONS_FILE)
                 logger.info(f"Registro de {member} ({discord_id_str}) removido.")

            kick_msg = config.get("kick_message", "Você foi removido do servidor por não fazer mais parte do clã.")
            try:
                 await member.send(kick_msg)
                 logger.info(f"Mensagem de expulsão enviada para {member}.")
            except discord.Forbidden:
                 logger.warning(f"Não foi possível enviar DM de expulsão para {member} (DMs desativadas?).")
            except Exception as e_dm:
                 logger.error(f"Erro ao enviar DM de expulsão para {member}: {e_dm}")

            await asyncio.sleep(1)

            try:
                await member.kick(reason="Não encontrado no clã durante verificação periódica.")
                logger.info(f"Membro {member} expulso do servidor.")
                log_channel_id = config.get("log_channel_id")
                if log_channel_id:
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel:
                        try: await log_channel.send(f"👢 Membro {member.mention} (`{discord_id_str}`) expulso automaticamente por não ser encontrado no clã com a tag `{expected_tag}`.")
                        except Exception: pass
            except discord.Forbidden:
                 logger.error(f"Falha ao expulsar {member}: Permissão 'Expulsar Membros' ausente ou hierarquia.")
                 log_channel_id = config.get("log_channel_id")
                 if log_channel_id:
                     log_channel = guild.get_channel(log_channel_id)
                     if log_channel:
                         try: await log_channel.send(f"⚠️ Falha ao expulsar {member.mention} (`{discord_id_str}`). Verificar permissões/hierarquia.")
                         except Exception: pass
            except Exception as e_kick:
                 logger.error(f"Erro inesperado ao expulsar {member}: {e_kick}")

    except coc_errors.NotFound:
        logger.warning(f"Clã {config['clan_tag']} não encontrado durante verificação de {member}.")
    except coc_errors.AuthenticationError:
        logger.critical(f"Erro de autenticação CoC durante verificação de {member}. Tentando relogar...")
        # Usa a global coc_client (declarada no início da função)
        coc_client = None
        await initialize_coc_client() # Tenta reinicializar o cliente global
    except coc_errors.ClashOfClansException as e_coc:
        logger.error(f"Erro API CoC ao verificar {member} ({expected_tag}): {e_coc}")
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ao verificar {member} ({expected_tag}).")
    except Exception as e:
        logger.error(f"Erro inesperado ao verificar membro {member}: {e}", exc_info=True)


# --- Tarefa de Verificação Periódica ---
@tasks.loop(hours=1)
async def verify_members_task():
    """Verifica periodicamente todos os membros registrados."""
    # Declaração global no início da função
    global coc_client
    global registrations

    # Usa as globais (declaradas acima)
    if not coc_client or not hasattr(coc_client, 'http') or not coc_client.http:
        logger.warning("Skipping verify_members_task: Cliente CoC não inicializado ou desconectado.")
        return
    if not config or "clan_tag" not in config:
        logger.warning("Skipping verify_members_task: Configuração do bot (clan_tag) ausente.")
        return
    if not bot.guilds:
        logger.warning("Skipping verify_members_task: Bot não está em nenhum servidor.")
        return

    regs_copy = registrations.copy()

    logger.info(f"--- Iniciando Tarefa de Verificação Periódica ({len(regs_copy)} membros registrados) ---")
    guild = bot.guilds[0]
    if not guild:
        logger.error("Não foi possível obter o objeto Guild na tarefa de verificação.")
        return

    verified_count = 0
    start_time = datetime.now()

    for discord_id_str, player_tag in regs_copy.items():
        member = guild.get_member(int(discord_id_str))
        if not member:
            logger.warning(f"Membro registrado ID {discord_id_str} (tag: {player_tag}) não encontrado no servidor {guild.name}. Removendo registro.")
            # Usa a global registrations (declarada no início da função)
            if discord_id_str in registrations:
                del registrations[discord_id_str]
                if not save_json(registrations, REGISTRATIONS_FILE):
                     logger.error(f"Falha ao salvar {REGISTRATIONS_FILE} após remover membro {discord_id_str} não encontrado.")
            continue

        await verify_single_member(member, player_tag, guild)
        verified_count += 1
        await asyncio.sleep(0.5)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"--- Tarefa de Verificação Periódica Concluída ---")
    logger.info(f"Verificados: {verified_count} membros em {duration:.2f} segundos.")

# --- Handler do Health Check para Render.com ---
async def health_check(request):
    """Responde com HTTP 200 OK para indicar que o serviço está rodando."""
    logger.debug("Health check recebido.")
    return web.Response(text="OK", status=200)

# --- Função Principal (main) ---
async def main():
    """Configura o servidor web auxiliar e inicia o bot Discord."""
    # Declaração global no início
    global coc_client

    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    try:
        await site.start()
        logger.info(f"Servidor web auxiliar iniciado em http://0.0.0.0:{PORT} para health checks do Render.")
    except Exception as e:
        logger.critical(f"Falha ao iniciar o servidor web auxiliar na porta {PORT}: {e}", exc_info=True)
        logger.warning("Tentando iniciar o bot Discord mesmo sem o servidor web auxiliar (PODE NÃO FUNCIONAR NO RENDER)...")

    try:
        logger.info("Iniciando bot Discord...")
        await bot.start(TOKEN)
    except discord.LoginFailure:
        logger.critical("Token Discord inválido! Verifique seu arquivo .env")
    except Exception as e:
        logger.critical(f"Erro fatal durante a execução do bot: {e}", exc_info=True)
    finally:
        logger.info("Parando o bot e limpando recursos...")
        await runner.cleanup()
        logger.info("Runner do AIOHTTP limpo.")
        # Usa a global coc_client (declarada no início de main)
        if coc_client:
            try:
                await coc_client.close()
                logger.info("Cliente CoC fechado.")
            except Exception as e_close:
                 logger.error(f"Erro ao fechar cliente CoC: {e_close}")

# --- Ponto de Entrada ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Erro não tratado na execução principal: {e}", exc_info=True)
