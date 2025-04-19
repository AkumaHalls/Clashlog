# 🤖 Clash Log Bot - Seu Assistente CoC Mágico no Discord! ✨🏰

[![Discord.py](https://img.shields.io/badge/Discord.py-v2.x-blue?style=flat-square&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/en/latest/) [![Python-ClashOfClans](https://img.shields.io/badge/Python--ClashOfClans-Library-orange?style=flat-square)](https://github.com/mathsman5133/python-clashofclans)

E aí, Chefe! 👋 Cansado de gerenciar manualmente os cargos do Discord baseados no seu clã do Clash of Clans? Seus problemas acabaram! 🎉

O **Clash Log Bot** chegou para automatizar tudo! Este bot incrível sincroniza os cargos dos membros no seu servidor Discord com os cargos deles dentro do seu clã no Clash of Clans. Mantenha tudo organizado e atualizado sem levantar um dedo (ou quase! 😉).

---

## 🔥 Funcionalidades Principais 🔥

* ✅ **Registro Inteligente:** Membros do clã podem solicitar registro usando a tag do jogador CoC.
* 🛂 **Sistema de Aprovação:** Admins recebem as solicitações e podem aprovar ou negar, garantindo controle total.
* 🛡️ **Sincronização de Cargos:** Mapeia cargos CoC (Membro, Ancião, Colíder, Líder) para cargos específicos no Discord.
* 🔄 **Verificação Automática:** O bot verifica periodicamente se os membros registrados AINDA estão no clã e com o cargo correto.
* 👢 **Gerenciamento Automático:** Remove cargos ou até expulsa membros que saíram do clã, mantendo seu servidor limpo!
* ⚙️ **Configuração Fácil:** Um comando simples (`/setup`) para configurar tudo que o bot precisa.
* 📄 **Logging Detalhado:** Registra ações importantes (aprovações, negações, expulsões) em um canal específico.
* ☁️ **Pronto para Deploy:** Preparado com um health check para rodar em plataformas como Render.com!

---

## 🚀 Comandos do Bot 🚀

Aqui está a mágica que você pode fazer:

### 👤 Comandos para Membros 👤

* `/registrar <player_tag>` 📝
    * **O quê?** Permite que um membro solicite o registro no servidor usando sua tag do Clash of Clans (Ex: `#ABC123XYZ`).
    * **Como funciona?** O bot verifica se a tag pertence a um membro do clã configurado. Se sim, envia uma solicitação para o canal de aprovações para os admins avaliarem. ✨
    * **Onde usar?** Apenas no canal de registro definido pelo Admin no `/setup`.

### 🔑 Comandos para Administradores 🔑

* `/setup [opções...]` ⚙️🛠️
    * **O quê?** O comando MESTRE para configurar o bot pela primeira vez ou alterar as configurações. **(Só Admins!)**
    * **Opções:**
        * `clan_tag`: A tag do SEU clã CoC (Ex: `#CLANTAG`).
        * `registration_channel`: O canal onde membros usarão `/registrar`.
        * `log_channel`: O canal para onde o bot enviará logs gerais (quem foi aprovado, negado, expulso).
        * `approval_log_channel`: O canal ONDE as solicitações de `/registrar` aparecerão para serem aprovadas/negadas.
        * `member_role`: O cargo Discord para membros comuns do clã.
        * `elder_role`: O cargo Discord para Anciãos (e Admins do CoC).
        * `coleader_role`: O cargo Discord para Co-líderes (e o Líder do CoC).
        * `kick_message` (Opcional): Mensagem personalizada enviada ao membro antes de ser expulso automaticamente.
    * **Importante:** Use este comando primeiro! Sem ele, o bot não funciona direito.

* `/aprovar usuario:<@Usuario> player_tag:<#TAG>` ✅👍
    * **O quê?** Aprova uma solicitação de registro pendente feita por um usuário. **(Só Admins!)**
    * **Como funciona?** O bot verifica NOVAMENTE se o jogador com a tag informada está no clã, pega o cargo CoC dele, remove cargos antigos do bot se houver, e atribui o cargo Discord correto (definido no `/setup`). Ele também salva o registro do usuário! 💾 O usuário é notificado por DM (se possível).
    * **Onde usar?** Em qualquer canal, mas geralmente usado após ver a solicitação no canal de aprovações.

* `/negar usuario:<@Usuario> player_tag:<#TAG> [motivo:<Texto>]` ❌👎
    * **O quê?** Nega uma solicitação de registro pendente. **(Só Admins!)**
    * **Como funciona?** Simplesmente marca a solicitação como negada e registra no canal de logs. Se um motivo for fornecido, o bot tenta enviar uma DM para o usuário informando o motivo da negação. 🚫
    * **Onde usar?** Em qualquer canal.

---

## ⏰ Verificação Automática em Background 🔄🧹

Este bot tem um superpoder secreto! 🦸‍♂️ A cada hora (configurado em `tasks.loop`), ele silenciosamente faz o seguinte:

1.  🌍 Pega a lista de TODOS os membros do Discord que foram **aprovados** e registrados.
2.  🔍 Para cada membro registrado, ele verifica na API do Clash of Clans:
    * O jogador com a tag registrada AINDA está no clã configurado?
    * Se sim, qual o cargo CoC atual dele?
3.  ⚙️ **Ajusta os Cargos:**
    * Se o membro está no clã com o cargo certo, mas não tem o cargo Discord correspondente (ou tem um cargo errado do bot), o bot corrige! ✨
    * Se o membro está no clã, mas subiu ou desceu de cargo CoC, o bot atualiza o cargo Discord! ⬆️⬇️
4.  👢 **Expulsão Automática:**
    * Se o membro registrado NÃO é mais encontrado no clã CoC... TCHAU! 👋 O bot remove todos os cargos CoC do Discord e o expulsa do servidor (enviando a `kick_message` antes, se configurada). Isso mantém seu servidor sincronizado APENAS com membros atuais do clã!

Este ciclo garante que, mesmo que as coisas mudem no CoC, seu Discord refletirá essas mudanças automaticamente!

---

## 🛠️ Configuração Inicial 🛠️

Para fazer essa belezinha funcionar:

1.  **Arquivo `.env` 🤫:** Crie um arquivo chamado `.env` na mesma pasta do bot. Ele guarda suas informações secretas! Preencha assim:

    ```dotenv
    DISCORD_TOKEN=SEU_TOKEN_SECRETO_DO_BOT_AQUI
    COC_EMAIL=SEU_EMAIL_DA_CONTA_SUPERCELL_AQUI
    COC_PASSWORD=SUA_SENHA_DA_CONTA_SUPERCELL_AQUI
    PORT=8080 # Necessário para deploy (Render.com), pode deixar 8080 se rodar local
    ```

    * **IMPORTANTE:** Obtenha um token de API do CoC em [https://developer.clashofclans.com/](https://developer.clashofclans.com/) e use-o em vez de Email/Senha se possível. A autenticação por Email/Senha pode ser menos estável e exigir verificação. Se usar chaves API, ajuste a inicialização do `coc.Client` no código. Por enquanto, o código usa Email/Senha.
    * **NUNCA** compartilhe seu arquivo `.env` ou seus tokens/senhas! Adicione `.env` ao seu arquivo `.gitignore` se usar Git.

2.  **Comando `/setup` ✨:** Depois que o bot estiver online no seu servidor, um Admin precisa usar o comando `/setup` (como descrito acima) para dizer ao bot qual clã monitorar, quais canais usar e quais cargos atribuir.

---

## 💻 Instalação e Execução ⚙️▶️

1.  **Clone ou Baixe:** Obtenha os arquivos do bot (`clash.py`, etc.).
2.  **Crie o `.env`:** Como descrito acima.
3.  **Instale as Dependências:** Abra um terminal na pasta do bot e rode:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Execute o Bot:**
    ```bash
    python clash.py
    ```
5.  **Convide o Bot:** Use o link de convite gerado no portal de desenvolvedores do Discord (com as permissões corretas!) para adicionar o bot ao seu servidor.
6.  **Configure:** Use o `/setup`!

---

## ☁️ Deploy (Ex: Render.com) ☁️

Este bot foi preparado para rodar em plataformas como o Render.com!

* Ele já inclui um servidor web `aiohttp` simples que responde na porta definida pela variável de ambiente `PORT`.
* Ao fazer deploy no Render, escolha o tipo "Web Service".
* Configure as variáveis de ambiente (`DISCORD_TOKEN`, `COC_EMAIL`, `COC_PASSWORD`) no painel do Render. O `PORT` será definido automaticamente pela plataforma.
* Use `python clash.py` como comando de início (Start Command).
* Certifique-se que seu `requirements.txt` está correto!

---

## 📄 Arquivos Importantes 📄

* `clash.py`: O coração do bot, todo o código Python está aqui. 🧠
* `requirements.txt`: Lista as bibliotecas Python necessárias. 📦
* `.env`: Guarda suas credenciais secretas (NÃO COMPARTILHE!). 🔑
* `config.json`: Salva as configurações definidas pelo comando `/setup`. ⚙️
* `registrations.json`: Guarda o mapeamento entre IDs do Discord e Tags CoC dos membros aprovados. 💾
* `registro_bot.log`: Arquivo de log detalhado para debugging e acompanhamento. 📜

---

Divirta-se automatizando seu servidor Discord com o poder do Clash of Clans! 💪 Se tiver dúvidas ou sugestões, sinta-se à vontade para contribuir (se for um projeto aberto) ou contatar o desenvolvedor. 🤓
