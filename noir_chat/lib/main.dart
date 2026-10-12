import 'dart:math';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

const supabaseUrl = 'https://mcywiaohezmgenzapxby.supabase.co';
const supabasePublishableKey = 'sb_publishable_rnAfWcfhihMzFyL7WWeZmQ_7KkzEwaq';
const blue = Color(0xFF527DA3);
const accent = Color(0xFF5E9DD5);
const pageBg = Color(0xFFF4F6F8);
const muted = Color(0xFF7B8790);
final supabase = Supabase.instance.client;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Supabase.initialize(url: supabaseUrl, anonKey: supabasePublishableKey);
  runApp(const DolbagramApp());
}

class DolbagramApp extends StatelessWidget {
  const DolbagramApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Dolbagram', debugShowCheckedModeBanner: false,
    theme: ThemeData(useMaterial3: true, brightness: Brightness.light,
      scaffoldBackgroundColor: pageBg,
      colorScheme: ColorScheme.fromSeed(seedColor: accent),
      appBarTheme: const AppBarTheme(backgroundColor: blue, foregroundColor: Colors.white),
      inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: Colors.white,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none))),
    home: const AuthGate(),
  );
}

class AuthGate extends StatelessWidget {
  const AuthGate({super.key});
  @override
  Widget build(BuildContext context) => StreamBuilder<AuthState>(
    stream: supabase.auth.onAuthStateChange,
    builder: (context, snapshot) => supabase.auth.currentSession == null ? const LoginScreen() : const HomeScreen(),
  );
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final phone = TextEditingController();
  final code = TextEditingController();
  final displayName = TextEditingController();
  bool codeSent = false, busy = false;
  String? error;
  String? notice;

  @override
  void dispose() {
    phone.dispose();
    code.dispose();
    displayName.dispose();
    super.dispose();
  }

  String get normalizedPhone => phone.text.trim().replaceAll(RegExp(r'[\\s()-]'), '');

  Future<void> requestCode() async {
    setState(() { busy = true; error = null; notice = null; });
    try {
      if (displayName.text.trim().length < 2) {
        throw const AuthException('Укажи имя минимум из 2 символов.');
      }
      final value = normalizedPhone;
      if (!RegExp(r'^\\+[1-9]\\d{7,14}$').hasMatch(value)) {
        throw const AuthException('Введи номер в международном формате, например +491234567890.');
      }
      await supabase.auth.signInWithOtp(
        phone: value,
        shouldCreateUser: true,
        data: {'display_name': displayName.text.trim()},
      );
      if (mounted) setState(() {
        codeSent = true;
        notice = 'Если номер поддерживается, код отправлен по SMS.';
      });
    } on AuthException catch (e) {
      if (mounted) setState(() => error = e.message);
    } catch (_) {
      if (mounted) setState(() => error = 'Не удалось отправить код. Проверь номер и соединение.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> verifyCode() async {
    setState(() { busy = true; error = null; notice = null; });
    try {
      final value = normalizedPhone;
      if (code.text.trim().length < 4) {
        throw const AuthException('Введи код из SMS.');
      }
      await supabase.auth.verifyOTP(
        phone: value,
        token: code.text.trim(),
        type: OtpType.sms,
      );
    } on AuthException catch (e) {
      if (mounted) setState(() => error = e.message);
    } catch (_) {
      if (mounted) setState(() => error = 'Не удалось подтвердить код. Попробуй ещё раз.');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: const Color(0xFF1D2935),
    body: SafeArea(child: Center(child: SingleChildScrollView(
      padding: const EdgeInsets.all(26),
      child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 420), child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Container(height: 92, alignment: Alignment.center,
            decoration: BoxDecoration(color: const Color(0xFF279FEA), borderRadius: BorderRadius.circular(30)),
            child: const Icon(Icons.send_rounded, color: Colors.white, size: 48)),
          const SizedBox(height: 20),
          const Text('Dolbagram', textAlign: TextAlign.center,
            style: TextStyle(fontSize: 30, fontWeight: FontWeight.w800, color: Colors.white)),
          const SizedBox(height: 8),
          Text(codeSent ? 'Введи код подтверждения' : 'Общайся по своему номеру телефона.',
            textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70)),
          const SizedBox(height: 28),
          if (!codeSent) ...[
            TextField(controller: displayName, textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(labelText: 'Как тебя называть?', prefixIcon: Icon(Icons.person_outline))),
            const SizedBox(height: 12),
            TextField(controller: phone, keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Номер телефона', hintText: '+491234567890', prefixIcon: Icon(Icons.phone_outlined))),
          ] else ...[
            Text('Код отправлен на ${normalizedPhone}', textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 12),
            TextField(controller: code, keyboardType: TextInputType.number, autofocus: true,
              maxLength: 8, decoration: const InputDecoration(labelText: 'Код из SMS', prefixIcon: Icon(Icons.sms_outlined))),
          ],
          if (notice != null) ...[const SizedBox(height: 12), Text(notice!, style: const TextStyle(color: Colors.lightGreenAccent))],
          if (error != null) ...[const SizedBox(height: 12), Text(error!, style: const TextStyle(color: Colors.redAccent))],
          const SizedBox(height: 18),
          FilledButton(onPressed: busy ? null : (codeSent ? verifyCode : requestCode),
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF279FEA), padding: const EdgeInsets.all(15)),
            child: Text(busy ? 'Подожди…' : codeSent ? 'Подтвердить код' : 'Получить код по SMS')),
          if (codeSent) TextButton(onPressed: busy ? null : () => setState(() {
            codeSent = false; code.clear(); error = null; notice = null;
          }), child: const Text('Изменить номер', style: TextStyle(color: Colors.white70))),
          const SizedBox(height: 12),
          const Text('После входа за тобой закрепляется NOIR ID.',
            textAlign: TextAlign.center, style: TextStyle(color: Colors.white60, fontSize: 12)),
        ],
      )),
    ))),
  );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override State<HomeScreen> createState() => _HomeScreenState();
}
class _HomeScreenState extends State<HomeScreen> {
  int tab = 0;
  bool loading = true;
  String search = '', displayName = 'Пользователь', noirId = 'NOIR-…';
  String? loadError;
  List<Map<String, dynamic>> conversations = [];
  Set<String> joined = {};

  @override void initState() { super.initState(); loadHome(); }

  Future<void> loadHome() async {
    setState(() { loading = true; loadError = null; });
    try {
      final user = supabase.auth.currentUser!;
      final profile = await supabase.from('dolbagram_profiles').select('display_name,noir_id').eq('id', user.id).maybeSingle();
      final memberships = await supabase.from('dolbagram_conversation_members').select('conversation_id').eq('user_id', user.id);
      final memberIds = memberships.map((e) => e['conversation_id'].toString()).toSet();
      final publicRows = await supabase.from('dolbagram_conversations').select('id,kind,title,description,is_public,updated_at').eq('is_public', true).order('updated_at');
      final privateRows = memberIds.isEmpty ? <Map<String, dynamic>>[] :
        List<Map<String, dynamic>>.from(await supabase.from('dolbagram_conversations').select('id,kind,title,description,is_public,updated_at').inFilter('id', memberIds.toList()));
      final merged = <String, Map<String, dynamic>>{};
      for (final row in publicRows) { merged[row['id'].toString()] = Map<String, dynamic>.from(row); }
      for (final row in privateRows) { merged[row['id'].toString()] = Map<String, dynamic>.from(row); }
      for (final row in merged.values.where((r) => r['kind'] == 'direct')) {
        final peers = await supabase.from('dolbagram_conversation_members').select('user_id').eq('conversation_id', row['id']);
        final peerIds = peers.map((m) => m['user_id'].toString()).where((id) => id != user.id).toList();
        final peer = peerIds.isEmpty ? null : peerIds.first;
        if (peer != null) {
          final peerProfile = await supabase.from('dolbagram_profiles').select('display_name,username').eq('id', peer).maybeSingle();
          row['title'] = peerProfile?['display_name'] ?? peerProfile?['username'] ?? 'Личный чат';
          row['description'] = 'Личный чат';
        }
      }
      if (!mounted) return;
      setState(() {
        displayName = (profile?['display_name'] as String?) ?? user.email?.split('@').first ?? 'Пользователь';
        noirId = (profile?['noir_id'] as String?) ?? 'NOIR-…';
        joined = memberIds;
        conversations = merged.values.toList();
        loading = false;
      });
    } catch (_) {
      if (mounted) setState(() { loading = false; loadError = 'Не удалось загрузить чаты. Проверь настройки базы данных и соединение.'; });
    }
  }

  Future<void> openChat(Map<String, dynamic> c) async {
    final id = c['id'].toString();
    try {
      if (!joined.contains(id)) {
        await supabase.from('dolbagram_conversation_members').insert({'conversation_id': id, 'user_id': supabase.auth.currentUser!.id});
        joined.add(id);
      }
      if (!mounted) return;
      await Navigator.push(context, MaterialPageRoute(builder: (_) => ChatScreen(conversation: c, myName: displayName)));
      loadHome();
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Не удалось войти в чат. Попробуй ещё раз.')));
    }
  }

  String newUuid() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  Future<void> chooseUser() async {
    try {
      final rows = await supabase.from('dolbagram_profiles').select('id,username,display_name,noir_id')
        .neq('id', supabase.auth.currentUser!.id).order('display_name');
      if (!mounted) return;
      final selected = await showDialog<Map<String, dynamic>>(context: context, builder: (ctx) {
        String query = '';
        return StatefulBuilder(builder: (ctx, refresh) {
          final filtered = List<Map<String, dynamic>>.from(rows).where((u) =>
            ('${u['display_name']} ${u['username']} ${u['noir_id']}').toLowerCase().contains(query.toLowerCase())).toList();
          return AlertDialog(
            title: const Text('Новый личный чат'),
            content: SizedBox(width: double.maxFinite, height: 420, child: Column(children: [
              TextField(onChanged: (v) => refresh(() => query = v), decoration: const InputDecoration(hintText: 'Поиск по имени или NOIR ID', prefixIcon: Icon(Icons.search))),
              const SizedBox(height: 8),
              Expanded(child: filtered.isEmpty ? const Center(child: Text('Пользователи не найдены')) : ListView.builder(
                itemCount: filtered.length,
                itemBuilder: (_, i) {
                  final u = filtered[i];
                  return ListTile(
                    leading: const CircleAvatar(backgroundColor: Color(0xFFDDECF8), child: Icon(Icons.person, color: blue)),
                    title: Text(u['display_name']?.toString() ?? u['username']?.toString() ?? 'Пользователь'),
                    subtitle: Text('${u['noir_id']} · @${u['username']}'),
                    onTap: () => Navigator.pop(ctx, u),
                  );
                },
              )),
            ])),
            actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена'))],
          );
        });
      });
      if (selected != null) await createDirectChat(selected);
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Не удалось загрузить список пользователей.')));
    }
  }

  Future<void> createDirectChat(Map<String, dynamic> target) async {
    final me = supabase.auth.currentUser!.id;
    final id = newUuid();
    final targetName = target['display_name']?.toString() ?? target['username']?.toString() ?? 'Личный чат';
    try {
      await supabase.from('dolbagram_conversations').insert({
        'id': id, 'kind': 'direct', 'title': targetName, 'description': 'Личный чат',
        'is_public': false, 'created_by': me,
      });
      await supabase.from('dolbagram_conversation_members').insert({'conversation_id': id, 'user_id': me, 'role': 'owner'});
      await supabase.from('dolbagram_conversation_members').insert({'conversation_id': id, 'user_id': target['id'], 'role': 'member'});
      final conversation = <String, dynamic>{
        'id': id, 'kind': 'direct', 'title': targetName, 'description': 'Личный чат',
        'is_public': false, 'updated_at': DateTime.now().toIso8601String(),
      };
      if (!mounted) return;
      setState(() { joined.add(id); conversations.add(conversation); });
      await Navigator.push(context, MaterialPageRoute(builder: (_) => ChatScreen(conversation: conversation, myName: displayName)));
      loadHome();
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Не удалось создать личный чат.')));
    }
  }

  Future<void> editDisplayName() async {
    final controller = TextEditingController(text: displayName);
    final value = await showDialog<String>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Изменить имя'),
      content: TextField(controller: controller, maxLength: 40, decoration: const InputDecoration(labelText: 'Имя в Dolbagram')),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
        FilledButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('Сохранить')),
      ],
    ));
    controller.dispose();
    if (value == null || value.length < 2) return;
    try {
      await supabase.from('dolbagram_profiles').update({'display_name': value}).eq('id', supabase.auth.currentUser!.id);
      if (mounted) setState(() => displayName = value);
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Не удалось сохранить имя.')));
    }
  }

  Future<void> showProfile() async {
    await showModalBottomSheet<void>(context: context, showDragHandle: true, builder: (ctx) => SafeArea(
      child: Padding(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, children: [
        const CircleAvatar(radius: 32, backgroundColor: Color(0xFFDDECF8), child: Icon(Icons.person, size: 35, color: blue)),
        const SizedBox(height: 12), Text(displayName, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4), Text(noirId, style: const TextStyle(color: muted)),
        Text(supabase.auth.currentUser?.email ?? '', style: const TextStyle(color: muted)),
        const SizedBox(height: 12),
        OutlinedButton.icon(onPressed: () { Navigator.pop(ctx); editDisplayName(); },
          icon: const Icon(Icons.edit), label: const Text('Изменить имя')),
        OutlinedButton.icon(onPressed: () async { Navigator.pop(ctx); await supabase.auth.signOut(); },
          icon: const Icon(Icons.logout), label: const Text('Выйти из аккаунта')),
      ])),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final filtered = conversations.where((c) => ('${c['title']} ${c['description']}').toLowerCase().contains(search.toLowerCase())).toList();
    final visible = tab == 1 ? filtered.where((c) => joined.contains(c['id'].toString())).toList() : filtered;
    return Scaffold(
      appBar: AppBar(title: const Text('Dolbagram', style: TextStyle(fontSize: 21, fontWeight: FontWeight.w600)),
        actions: [IconButton(onPressed: loadHome, icon: const Icon(Icons.refresh)), IconButton(onPressed: showProfile, icon: const Icon(Icons.person_outline))]),
      body: Column(children: [
        Container(color: blue, padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
          child: TextField(onChanged: (v) => setState(() => search = v),
            decoration: const InputDecoration(hintText: 'Поиск групп', prefixIcon: Icon(Icons.search)))),
        Container(color: Colors.white, child: Row(children: [_tabButton('ВСЕ ГРУППЫ', 0), _tabButton('МОИ ЧАТЫ', 1)])),
        Expanded(child: loading ? const Center(child: CircularProgressIndicator())
          : loadError != null ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(loadError!, textAlign: TextAlign.center), const SizedBox(height: 14), FilledButton(onPressed: loadHome, child: const Text('Повторить')),
            ])))
          : visible.isEmpty ? Center(child: Text(tab == 1 ? 'Ты пока не вступил ни в один чат.' : 'Ничего не найдено.', style: const TextStyle(color: muted)))
          : ListView.separated(itemCount: visible.length, separatorBuilder: (_, __) => const Divider(height: 1, indent: 82),
              itemBuilder: (context, i) => _chatTile(visible[i]))),
      ]),
      floatingActionButton: FloatingActionButton(backgroundColor: accent, foregroundColor: Colors.white,
        onPressed: chooseUser,
        child: const Icon(Icons.edit)),
      bottomNavigationBar: NavigationBar(backgroundColor: Colors.white, indicatorColor: const Color(0xFFDDECF8),
        selectedIndex: tab, onDestinationSelected: (v) { if (v == 2) { showProfile(); } else { setState(() => tab = v); } },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat), label: 'Чаты'),
          NavigationDestination(icon: Icon(Icons.people_outline), selectedIcon: Icon(Icons.people), label: 'Мои чаты'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Профиль'),
        ]),
    );
  }

  Widget _tabButton(String text, int value) => Expanded(child: InkWell(onTap: () => setState(() => tab = value),
    child: Container(height: 44, alignment: Alignment.center,
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: tab == value ? accent : Colors.transparent, width: 3))),
      child: Text(text, style: TextStyle(color: tab == value ? accent : muted, fontSize: 12, fontWeight: FontWeight.w700)))));

  Widget _chatTile(Map<String, dynamic> c) {
    final title = c['title'] as String? ?? 'Чат';
    final isJoined = joined.contains(c['id'].toString());
    final colors = [const Color(0xFF5E9DD5), const Color(0xFF53A88C), const Color(0xFFD49B58), const Color(0xFFAA83D6)];
    final color = colors[title.hashCode.abs() % colors.length];
    return Material(color: Colors.white, child: InkWell(onTap: () => openChat(c),
      child: Padding(padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10), child: Row(children: [
        CircleAvatar(radius: 27, backgroundColor: color.withOpacity(.16), child: Text(title[0].toUpperCase(), style: TextStyle(color: color, fontSize: 23))),
        const SizedBox(width: 13),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontSize: 16, color: Color(0xFF17212B), fontWeight: FontWeight.w600)),
          const SizedBox(height: 5), Text(c['description'] as String? ?? '', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13, color: muted)),
        ])),
        Icon(isJoined ? Icons.check_circle : Icons.chevron_right, color: isJoined ? accent : muted, size: 18),
      ]))));
  }
}

class ChatScreen extends StatefulWidget {
  final Map<String, dynamic> conversation;
  final String myName;
  const ChatScreen({super.key, required this.conversation, required this.myName});
  @override State<ChatScreen> createState() => _ChatScreenState();
}
class _ChatScreenState extends State<ChatScreen> {
  final input = TextEditingController();
  late final Stream<List<Map<String, dynamic>>> messages;
  Map<String, String> names = {};
  bool sending = false;
  String? sendError;
  String get conversationId => widget.conversation['id'].toString();

  @override void initState() {
    super.initState();
    messages = supabase.from('dolbagram_messages').stream(primaryKey: ['id']).eq('conversation_id', conversationId).order('created_at');
    loadNames();
  }
  Future<void> loadNames() async {
    try {
      final rows = await supabase.from('dolbagram_profiles').select('id,display_name,username');
      if (mounted) setState(() => names = {for (final r in rows) r['id'].toString(): (r['display_name'] as String?) ?? (r['username'] as String? ?? 'Пользователь')});
    } catch (_) {}
  }
  @override void dispose() { input.dispose(); super.dispose(); }

  Future<void> sendMessage() async {
    final body = input.text.trim();
    if (body.isEmpty || sending) return;
    setState(() { sending = true; sendError = null; });
    try {
      await supabase.from('dolbagram_messages').insert({'conversation_id': conversationId, 'sender_id': supabase.auth.currentUser!.id, 'body': body});
      input.clear();
    } catch (_) { if (mounted) setState(() => sendError = 'Не отправилось. Проверь соединение и повтори.'); }
    finally { if (mounted) setState(() => sending = false); }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(titleSpacing: 0, title: Row(children: [
      CircleAvatar(backgroundColor: Colors.white.withOpacity(.2), child: Text((widget.conversation['title'] as String? ?? 'D')[0].toUpperCase(), style: const TextStyle(color: Colors.white))),
      const SizedBox(width: 10), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(widget.conversation['title'] as String? ?? 'Чат', style: const TextStyle(fontSize: 16)),
        const Text('Групповой чат', style: TextStyle(fontSize: 11, color: Colors.white70)),
      ])),
    ])),
    body: Column(children: [
      Expanded(child: StreamBuilder<List<Map<String, dynamic>>>(stream: messages, builder: (context, snapshot) {
        if (snapshot.hasError) return const Center(child: Text('Не удалось загрузить сообщения.'));
        if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
        final list = snapshot.data!;
        if (list.isEmpty) return const Center(child: Text('Пока нет сообщений. Напиши первым!', style: TextStyle(color: muted)));
        return ListView.builder(padding: const EdgeInsets.all(12), itemCount: list.length, itemBuilder: (context, i) {
          final m = list[i]; final mine = m['sender_id'] == supabase.auth.currentUser?.id;
          final name = mine ? widget.myName : (names[m['sender_id'].toString()] ?? 'Пользователь');
          final dt = DateTime.tryParse(m['created_at']?.toString() ?? '')?.toLocal();
          final time = dt == null ? '' : '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
          return Align(alignment: mine ? Alignment.centerRight : Alignment.centerLeft, child: Container(
            constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * .82),
            margin: const EdgeInsets.only(bottom: 8), padding: const EdgeInsets.fromLTRB(12, 8, 12, 7),
            decoration: BoxDecoration(color: mine ? const Color(0xFFDCECF9) : Colors.white, borderRadius: BorderRadius.circular(15)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (!mine) Padding(padding: const EdgeInsets.only(bottom: 4), child: Text(name, style: const TextStyle(color: blue, fontSize: 12, fontWeight: FontWeight.bold))),
              Text(m['body']?.toString() ?? '', style: const TextStyle(fontSize: 15, color: Color(0xFF17212B), height: 1.3)),
              const SizedBox(height: 3), Align(alignment: Alignment.bottomRight, child: Text(time, style: const TextStyle(color: muted, fontSize: 10))),
            ]),
          ));
        });
      })),
      if (sendError != null) Padding(padding: const EdgeInsets.symmetric(horizontal: 14), child: Align(alignment: Alignment.centerLeft, child: Text(sendError!, style: const TextStyle(color: Colors.red, fontSize: 12)))),
      SafeArea(top: false, child: Container(color: Colors.white, padding: const EdgeInsets.all(8), child: Row(children: [
        const Padding(padding: EdgeInsets.symmetric(horizontal: 7), child: Icon(Icons.attach_file, color: muted)),
        Expanded(child: TextField(controller: input, textInputAction: TextInputAction.send, onSubmitted: (_) => sendMessage(),
          decoration: const InputDecoration(hintText: 'Сообщение…', fillColor: pageBg, contentPadding: EdgeInsets.symmetric(horizontal: 15, vertical: 11)))),
        const SizedBox(width: 7),
        IconButton.filled(onPressed: sending ? null : sendMessage, style: IconButton.styleFrom(backgroundColor: accent, foregroundColor: Colors.white),
          icon: sending ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.send_rounded)),
      ]))),
    ]),
  );
}
