import 'package:flutter/material.dart';

void main() => runApp(const DolbagramApp());

const bg = Color(0xFFF4F6F8);
const panel = Color(0xFFFFFFFF);
const violet = Color(0xFF5E9DD5);
const cyan = Color(0xFF5E9DD5);
const muted = Color(0xFF7B8790);

class DolbagramApp extends StatelessWidget {
  const DolbagramApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Dolbagram',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(useMaterial3: true, brightness: Brightness.light,
      scaffoldBackgroundColor: bg,
      colorScheme: const ColorScheme.light(primary: violet, secondary: cyan, surface: panel),
      inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: const Color(0xFFF0F2F5),
        hintStyle: const TextStyle(color: muted),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide.none))),
    home: const HomeScreen());
}

class Room {
  final String name, topic, icon, preview;
  final Color color;
  final int members;
  const Room(this.name, this.topic, this.icon, this.color, this.members, this.preview);
}
const rooms = [
  Room('Late Night', 'Разговоры после полуночи', '☾', violet, 128, 'Кто ещё не спит?'),
  Room('Mindspace', 'Идеи, мысли и открытия', '✳', cyan, 84, 'Сегодня задумался о будущем…'),
  Room('Indie Corner', 'Музыка, кино и творчество', '♫', Color(0xFFFFA66D), 56, 'Нашёл невероятный альбом'),
  Room('Quiet Club', 'Можно просто быть собой', '♡', Color(0xFFFF7DAA), 42, 'Рад, что вы здесь'),
];

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}
class _HomeScreenState extends State<HomeScreen> {
  int tab = 0;
  String nickname = 'midnight';
  String search = '';
  final joined = <String>{'Late Night', 'Mindspace'};

  @override
  Widget build(BuildContext context) {
    final filtered = rooms.where((r) => ('${r.name} ${r.topic} ${r.preview}').toLowerCase().contains(search.toLowerCase())).toList();
    return Scaffold(
      backgroundColor: const Color(0xFFF4F6F8),
      appBar: AppBar(
        backgroundColor: const Color(0xFF527DA3),
        foregroundColor: Colors.white,
        title: const Text('Dolbagram', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 21)),
        actions: [
          IconButton(onPressed: editNickname, icon: const Icon(Icons.edit_note_rounded)),
          IconButton(onPressed: () => setState(() => tab = 1), icon: const Icon(Icons.message_outlined)),
        ],
      ),
      body: Column(children: [
        Container(
          color: const Color(0xFF527DA3),
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
          child: TextField(
            onChanged: (v) => setState(() => search = v),
            decoration: InputDecoration(
              hintText: 'Поиск',
              prefixIcon: const Icon(Icons.search, color: Color(0xFF7C8A96)),
              filled: true, fillColor: Colors.white,
              contentPadding: const EdgeInsets.symmetric(vertical: 0),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
            ),
          ),
        ),
        Container(
          color: Colors.white,
          child: Row(children: [
            _tabButton('ВСЕ ЧАТЫ', 0),
            _tabButton('ГРУППЫ', 1),
          ]),
        ),
        Expanded(child: ListView.separated(
          itemCount: filtered.length,
          separatorBuilder: (_, __) => const Divider(height: 1, indent: 82, color: Color(0xFFE8EAED)),
          itemBuilder: (context, i) => _chatTile(filtered[i]),
        )),
      ]),
      floatingActionButton: FloatingActionButton(
        backgroundColor: const Color(0xFF5E9DD5),
        foregroundColor: Colors.white,
        onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Новые личные чаты появятся после подключения сервера.')),
        ),
        child: const Icon(Icons.edit),
      ),
      bottomNavigationBar: NavigationBar(
        backgroundColor: Colors.white,
        indicatorColor: const Color(0xFFDDECF8),
        selectedIndex: tab,
        onDestinationSelected: (v) { if (v == 2) { editNickname(); } else { setState(() => tab = v); } },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat), label: 'Чаты'),
          NavigationDestination(icon: Icon(Icons.people_outline), selectedIcon: Icon(Icons.people), label: 'Группы'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Профиль'),
        ],
      ),
    );
  }

  Widget _tabButton(String text, int value) => Expanded(
    child: InkWell(onTap: () => setState(() => tab = value), child: Container(
      height: 44, alignment: Alignment.center,
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: tab == value ? const Color(0xFF5E9DD5) : Colors.transparent, width: 3))),
      child: Text(text, style: TextStyle(color: tab == value ? const Color(0xFF4F8FCA) : const Color(0xFF7C8792), fontSize: 12, fontWeight: FontWeight.w700)),
    )),
  );

  Widget _chatTile(Room room) => Material(
    color: Colors.white,
    child: InkWell(onTap: () => openRoom(room), child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(children: [
        CircleAvatar(radius: 27, backgroundColor: room.color.withOpacity(.18),
          child: Text(room.icon, style: TextStyle(color: room.color, fontSize: 25))),
        const SizedBox(width: 13),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(room.name, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 16, color: Color(0xFF17212B), fontWeight: FontWeight.w600))),
            const Text('23:41', style: TextStyle(fontSize: 11, color: Color(0xFF8A969F))),
          ]),
          const SizedBox(height: 5),
          Row(children: [
            Expanded(child: Text(tab == 0 ? room.preview : room.topic, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 13, color: Color(0xFF7B8790)))),
            if (joined.contains(room.name)) Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(color: const Color(0xFF5E9DD5), borderRadius: BorderRadius.circular(12)),
              child: Text('${room.members}', style: const TextStyle(color: Colors.white, fontSize: 10)),
            ),
          ]),
        ])),
      ]),
    )),
  );

  void openRoom(Room room) {
    setState(() => joined.add(room.name));
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => ChatScreen(room: room, nickname: nickname)));
  }

  void editNickname() {
    final c = TextEditingController(text: nickname);
    showDialog<void>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Профиль Dolbagram'),
      content: TextField(controller: c, maxLength: 20, decoration: const InputDecoration(labelText: 'Никнейм', prefixText: '@')),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
        FilledButton(onPressed: () { final v = c.text.trim().replaceAll(' ', '_'); if (v.isNotEmpty) setState(() => nickname = v); Navigator.pop(ctx); }, child: const Text('Сохранить')),
      ],
    ));
  }
}

class ChatScreen extends StatefulWidget {
  final Room room; final String nickname;
  const ChatScreen({super.key,required this.room,required this.nickname});
  @override State<ChatScreen> createState()=>_ChatScreenState();
}
class _ChatScreenState extends State<ChatScreen>{
  final input=TextEditingController();final scroll=ScrollController();
  late final List<Map<String,String>> messages;
  @override void initState(){super.initState();messages=[
    {'name':'nova','text':'Добро пожаловать в ${widget.room.name} ✨','time':'23:41'},
    {'name':'echo','text':widget.room.preview,'time':'23:43'},
    {'name':'luna','text':'Здесь можно просто быть собой.','time':'23:44'},
  ];}
  @override void dispose(){input.dispose();scroll.dispose();super.dispose();}
  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(backgroundColor:bg,titleSpacing:0,title:Row(children:[
      CircleAvatar(backgroundColor:widget.room.color.withOpacity(.14),child:Text(widget.room.icon,style:TextStyle(color:widget.room.color))),
      const SizedBox(width:10),Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        Text(widget.room.name,style:const TextStyle(fontSize:16,fontWeight:FontWeight.bold)),
        Text('${widget.room.members} участников · открытая комната',style:const TextStyle(color:muted,fontSize:10)),
      ]),
    ])),
    body:Column(children:[
      Container(margin:const EdgeInsets.fromLTRB(16,8,16,8),padding:const EdgeInsets.all(12),
        decoration:BoxDecoration(color:violet.withOpacity(.09),borderRadius:BorderRadius.circular(14)),
        child:const Row(children:[Icon(Icons.info_outline_rounded,color:violet,size:17),SizedBox(width:8),
          Expanded(child:Text('Демо-режим: сообщения пока видны только на этом устройстве.',style:TextStyle(color:muted,fontSize:11)))])),
      Expanded(child:ListView.builder(controller:scroll,padding:const EdgeInsets.fromLTRB(16,10,16,18),itemCount:messages.length,
        itemBuilder:(context,i){final m=messages[i];final mine=m['name']==widget.nickname;
          return Align(alignment:mine?Alignment.centerRight:Alignment.centerLeft,child:Container(
            constraints:BoxConstraints(maxWidth:MediaQuery.of(context).size.width*.78),margin:const EdgeInsets.only(bottom:13),
            padding:const EdgeInsets.fromLTRB(14,11,14,9),
            decoration:BoxDecoration(color:mine?const Color(0xFF3C3065):panel,borderRadius:BorderRadius.only(
              topLeft:const Radius.circular(18),topRight:const Radius.circular(18),
              bottomLeft:Radius.circular(mine?18:5),bottomRight:Radius.circular(mine?5:18))),
            child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
              if(!mine)Padding(padding:const EdgeInsets.only(bottom:5),child:Text('@${m['name']}',style:TextStyle(color:widget.room.color,fontSize:11,fontWeight:FontWeight.bold))),
              Text(m['text']!,style:const TextStyle(fontSize:14,height:1.35)),const SizedBox(height:5),
              Align(alignment:Alignment.bottomRight,child:Text(m['time']!,style:const TextStyle(color:muted,fontSize:9))),
            ])));
        })),
      SafeArea(top:false,child:Padding(padding:const EdgeInsets.fromLTRB(12,8,12,12),child:Row(children:[
        IconButton(onPressed:()=>ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Вложения появятся в следующей версии.'))),
          icon:const Icon(Icons.add_circle_outline_rounded,color:muted)),
        Expanded(child:TextField(controller:input,textInputAction:TextInputAction.send,onSubmitted:(_)=>sendMessage(),
          decoration:const InputDecoration(hintText:'Написать сообщение…',contentPadding:EdgeInsets.symmetric(horizontal:16,vertical:13)))),
        const SizedBox(width:8),IconButton.filled(onPressed:sendMessage,style:IconButton.styleFrom(backgroundColor:violet,foregroundColor:Colors.white),
          icon:const Icon(Icons.arrow_upward_rounded)),
      ]))),
    ]));
  void sendMessage(){final text=input.text.trim();if(text.isEmpty)return;setState((){
    messages.add({'name':widget.nickname,'text':text,'time':TimeOfDay.now().format(context)});input.clear();});
    WidgetsBinding.instance.addPostFrameCallback((_){if(scroll.hasClients)scroll.animateTo(scroll.position.maxScrollExtent+120,
      duration:const Duration(milliseconds:220),curve:Curves.easeOut);});
  }
}
