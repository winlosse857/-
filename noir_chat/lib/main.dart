import 'package:flutter/material.dart';

void main() => runApp(const DolbagramApp());

const bg = Color(0xFF090B12);
const panel = Color(0xFF151925);
const violet = Color(0xFF9B7BFF);
const cyan = Color(0xFF65E6D2);
const muted = Color(0xFF9299AD);

class DolbagramApp extends StatelessWidget {
  const DolbagramApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Dolbagram',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(useMaterial3: true, brightness: Brightness.dark,
      scaffoldBackgroundColor: bg,
      colorScheme: const ColorScheme.dark(primary: violet, secondary: cyan, surface: panel),
      inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: const Color(0xFF202536),
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
  final joined = <String>{'Late Night', 'Mindspace'};

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(child: CustomScrollView(slivers: [
      SliverToBoxAdapter(child: header()),
      SliverToBoxAdapter(child: welcome()),
      SliverToBoxAdapter(child: Padding(padding: const EdgeInsets.fromLTRB(22,0,22,10),
        child: Row(children: [chip('Комнаты',0), const SizedBox(width:9), chip('Сообщения',1)]))),
      SliverToBoxAdapter(child: Padding(padding: const EdgeInsets.fromLTRB(22,18,22,10),
        child: Text(tab == 0 ? 'КОМНАТЫ ПО ИНТЕРЕСАМ' : 'НЕДАВНИЕ ЧАТЫ',
          style: const TextStyle(color: muted,fontSize:10,letterSpacing:1.5,fontWeight:FontWeight.bold)))),
      SliverList(delegate: SliverChildBuilderDelegate((context,i)=>roomTile(rooms[i]),childCount:rooms.length)),
      const SliverToBoxAdapter(child:SizedBox(height:24)),
    ])),
    bottomNavigationBar: NavigationBar(backgroundColor:panel,indicatorColor:violet.withOpacity(.18),
      selectedIndex:tab,onDestinationSelected:(v){ if(v==2){editNickname();}else{setState(()=>tab=v);} },
      destinations:const [
        NavigationDestination(icon:Icon(Icons.grid_view_rounded),label:'Комнаты'),
        NavigationDestination(icon:Icon(Icons.chat_bubble_outline_rounded),label:'Чаты'),
        NavigationDestination(icon:Icon(Icons.person_outline_rounded),label:'Профиль'),
      ]),
  );

  Widget header()=>Padding(padding:const EdgeInsets.fromLTRB(22,16,18,8),child:Row(children:[
    Container(width:42,height:42,decoration:BoxDecoration(borderRadius:BorderRadius.circular(14),
      gradient:const LinearGradient(colors:[violet,Color(0xFF5B4BC4)])),
      child:const Icon(Icons.nightlight_round,color:Colors.white)),
    const SizedBox(width:12),
    const Text('Dolbagram',style:TextStyle(fontSize:20,letterSpacing:1.5,fontWeight:FontWeight.w800)),
    const Spacer(),
    Container(padding:const EdgeInsets.symmetric(horizontal:11,vertical:8),
      decoration:BoxDecoration(color:panel,borderRadius:BorderRadius.circular(20)),
      child:const Row(children:[Icon(Icons.circle,color:cyan,size:8),SizedBox(width:7),
        Text('В сети',style:TextStyle(color:muted,fontSize:12))])),
  ]));

  Widget welcome()=>Padding(padding:const EdgeInsets.fromLTRB(22,23,22,22),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
    const Text('ТВОЁ ПРОСТРАНСТВО',style:TextStyle(color:cyan,fontSize:10,letterSpacing:2,fontWeight:FontWeight.w700)),
    const SizedBox(height:12),
    const Text('Меньше шума.\nБольше настоящего.',style:TextStyle(fontSize:31,height:1.15,fontWeight:FontWeight.w700,letterSpacing:-.7)),
    const SizedBox(height:12),
    Text('Привет, @$nickname. Найди своих людей.',style:const TextStyle(color:muted,fontSize:14)),
    const SizedBox(height:20),
    Container(width:double.infinity,padding:const EdgeInsets.all(18),
      decoration:BoxDecoration(borderRadius:BorderRadius.circular(24),
        gradient:const LinearGradient(begin:Alignment.topLeft,end:Alignment.bottomRight,
          colors:[Color(0xFF292043),Color(0xFF171B2B),panel]),
        border:Border.all(color:violet.withOpacity(.25))),
      child:Row(children:[
        Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
          const Text('КОМНАТА ДНЯ',style:TextStyle(color:violet,fontSize:10,letterSpacing:1.7,fontWeight:FontWeight.bold)),
          const SizedBox(height:8),const Text('Late Night',style:TextStyle(fontSize:21,fontWeight:FontWeight.bold)),
          const SizedBox(height:4),const Text('Разговоры без лишних масок',style:TextStyle(color:muted,fontSize:11)),
          const SizedBox(height:14),
          FilledButton(onPressed:()=>openRoom(rooms[0]),style:FilledButton.styleFrom(backgroundColor:violet),child:const Text('Войти в комнату →')),
        ])),
        Container(width:66,height:78,decoration:BoxDecoration(color:violet.withOpacity(.13),borderRadius:BorderRadius.circular(22)),
          child:const Center(child:Text('☾',style:TextStyle(fontSize:42,color:violet)))),
      ])),
  ]));

  Widget chip(String label,int value){final active=tab==value;return GestureDetector(onTap:()=>setState(()=>tab=value),
    child:Container(padding:const EdgeInsets.symmetric(horizontal:16,vertical:10),
      decoration:BoxDecoration(color:active?violet.withOpacity(.18):panel,borderRadius:BorderRadius.circular(14),
        border:Border.all(color:active?violet.withOpacity(.45):Colors.transparent)),
      child:Text(label,style:TextStyle(color:active?Colors.white:muted,fontWeight:FontWeight.w600,fontSize:13))));}

  Widget roomTile(Room room)=>Padding(padding:const EdgeInsets.symmetric(horizontal:22,vertical:6),
    child:InkWell(borderRadius:BorderRadius.circular(20),onTap:()=>openRoom(room),
      child:Container(padding:const EdgeInsets.all(14),
        decoration:BoxDecoration(color:panel,borderRadius:BorderRadius.circular(20),border:Border.all(color:Colors.white.withOpacity(.035))),
        child:Row(children:[
          Container(width:52,height:52,decoration:BoxDecoration(color:room.color.withOpacity(.12),borderRadius:BorderRadius.circular(16)),
            child:Center(child:Text(room.icon,style:TextStyle(color:room.color,fontSize:27)))),
          const SizedBox(width:13),
          Expanded(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
            Text(room.name,style:const TextStyle(fontSize:15,fontWeight:FontWeight.w700)),
            const SizedBox(height:4),Text(tab==0?room.topic:room.preview,maxLines:1,overflow:TextOverflow.ellipsis,style:const TextStyle(color:muted,fontSize:11)),
            const SizedBox(height:7),Row(children:[Icon(Icons.circle,color:room.color,size:6),const SizedBox(width:5),
              Text('${room.members} участников',style:const TextStyle(color:muted,fontSize:10))]),
          ])),
          Icon(joined.contains(room.name)?Icons.arrow_forward_ios_rounded:Icons.add_rounded,color:room.color,size:18),
        ]))));

  void openRoom(Room room){setState(()=>joined.add(room.name));Navigator.of(context).push(MaterialPageRoute(builder:(_)=>ChatScreen(room:room,nickname:nickname)));}
  void editNickname(){
    final c=TextEditingController(text:nickname);
    showDialog<void>(context:context,builder:(ctx)=>AlertDialog(backgroundColor:panel,title:const Text('Твой профиль'),
      content:TextField(controller:c,maxLength:20,decoration:const InputDecoration(labelText:'Никнейм',prefixText:'@')),
      actions:[TextButton(onPressed:()=>Navigator.pop(ctx),child:const Text('Отмена')),
        FilledButton(onPressed:(){final v=c.text.trim().replaceAll(' ','_');if(v.isNotEmpty)setState(()=>nickname=v);Navigator.pop(ctx);},child:const Text('Сохранить'))]));
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
