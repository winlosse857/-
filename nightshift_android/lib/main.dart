import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Color(0xFF080B14),
    systemNavigationBarColor: Color(0xFF080B14),
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarIconBrightness: Brightness.light,
  ));
  runApp(const NightshiftApp());
}

const bg = Color(0xFF080B14);
const panel = Color(0xFF111827);
const cyan = Color(0xFF45F3FF);
const purple = Color(0xFFB56CFF);
const muted = Color(0xFF8B9BB4);

class NightshiftApp extends StatelessWidget {
  const NightshiftApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'NIGHTSHIFT',
    debugShowCheckedModeBanner: false,
    theme: ThemeData.dark().copyWith(
      scaffoldBackgroundColor: bg,
      colorScheme: const ColorScheme.dark(primary: cyan, secondary: purple),
      useMaterial3: true,
    ),
    home: const HomeScreen(),
  );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int best = 0;
  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.blur_on_rounded, color: cyan, size: 28),
          SizedBox(width: 9),
          Text('NEON ARCADE', style: TextStyle(letterSpacing: 3, color: muted, fontSize: 11, fontWeight: FontWeight.bold)),
          Spacer(),
          Icon(Icons.battery_3_bar, color: purple),
        ]),
        const Spacer(),
        const Text('NIGHT\nSHIFT', style: TextStyle(fontSize: 58, height: .94, fontWeight: FontWeight.w900, letterSpacing: -2)),
        const SizedBox(height: 18),
        const Text('Собери энергию. Найди выход.\nНе дай комплексу погаснуть.', style: TextStyle(color: muted, height: 1.6, fontSize: 15)),
        const SizedBox(height: 34),
        Container(
          width: double.infinity, height: 230,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF17243A), Color(0xFF101020), Color(0xFF1B1030)]),
            border: Border.all(color: cyan.withOpacity(.24)),
          ),
          child: CustomPaint(painter: PreviewPainter()),
        ),
        const Spacer(),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(18), border: Border.all(color: Colors.white.withOpacity(.06))),
          child: Row(children: [
            const Icon(Icons.emoji_events_outlined, color: purple, size: 28),
            const SizedBox(width: 12),
            const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('ЛУЧШИЙ РЕЗУЛЬТАТ', style: TextStyle(color: muted, fontSize: 10, letterSpacing: 1.5)),
              SizedBox(height: 4),
              Text('Твой забег начинается', style: TextStyle(fontWeight: FontWeight.bold)),
            ])),
            Text('$best', style: const TextStyle(color: cyan, fontSize: 24, fontWeight: FontWeight.bold)),
          ]),
        ),
        const SizedBox(height: 16),
        SizedBox(width: double.infinity, height: 58, child: FilledButton(
          style: FilledButton.styleFrom(backgroundColor: cyan, foregroundColor: bg, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
          onPressed: () async {
            final score = await Navigator.of(context).push<int>(MaterialPageRoute(builder: (_) => const GameScreen()));
            if (score != null && score > best && mounted) setState(() => best = score);
          },
          child: const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Text('НАЧАТЬ ИГРУ', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1.6)),
            SizedBox(width: 10), Icon(Icons.arrow_forward_rounded),
          ]),
        )),
        const SizedBox(height: 14),
        const Center(child: Text('ОФЛАЙН • БЕЗ РЕКЛАМЫ • БЕЗ ЛИШНЕГО', style: TextStyle(color: Color(0xFF526078), fontSize: 9, letterSpacing: 1.3))),
      ]),
    )),
  );
}

class PreviewPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()..color = cyan.withOpacity(.12)..strokeWidth = 1;
    for (double x = 18; x < size.width; x += 24) canvas.drawLine(Offset(x, 0), Offset(x, size.height), p);
    for (double y = 18; y < size.height; y += 24) canvas.drawLine(Offset(0, y), Offset(size.width, y), p);
    final glow = Paint()..color = cyan.withOpacity(.14)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 20);
    canvas.drawCircle(Offset(size.width * .5, size.height * .5), 55, glow);
    final orb = Paint()..color = cyan..style = PaintingStyle.stroke..strokeWidth = 3;
    canvas.drawCircle(Offset(size.width * .5, size.height * .5), 22, orb);
    canvas.drawCircle(Offset(size.width * .5, size.height * .5), 6, Paint()..color = cyan);
    final wall = Paint()..color = purple.withOpacity(.85)..strokeWidth = 5..strokeCap = StrokeCap.round;
    canvas.drawLine(Offset(30, 30), Offset(size.width * .35, 30), wall);
    canvas.drawLine(Offset(30, 30), Offset(30, size.height * .45), wall);
    canvas.drawLine(Offset(size.width * .72, size.height * .28), Offset(size.width - 24, size.height * .28), wall);
    canvas.drawLine(Offset(size.width - 24, size.height * .28), Offset(size.width - 24, size.height * .78), wall);
    canvas.drawCircle(Offset(size.width * .78, size.height * .72), 5, Paint()..color = purple);
    canvas.drawCircle(Offset(size.width * .22, size.height * .72), 5, Paint()..color = cyan);
  }
  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class GameScreen extends StatefulWidget {
  const GameScreen({super.key});
  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> {
  // # is a wall, . is a corridor, E is energy, X is the exit.
  final List<String> map = [
    '############',
    '#..E....#..#',
    '#.####..#..#',
    '#......##E.#',
    '###.##.....#',
    '#E..##.###.#',
    '#.#....#...#',
    '#.####.#.###',
    '#......#..X#',
    '############',
  ];
  int px = 1, py = 1, score = 0, energy = 24;
  bool ended = false, won = false;
  Timer? timer;

  @override
  void initState() {
    super.initState();
    timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!ended && mounted) setState(() {
        energy--;
        if (energy <= 0) { ended = true; won = false; }
      });
    });
  }
  @override
  void dispose() { timer?.cancel(); super.dispose(); }

  void move(int dx, int dy) {
    if (ended) return;
    final nx = px + dx, ny = py + dy;
    if (ny < 0 || ny >= map.length || nx < 0 || nx >= map[ny].length || map[ny][nx] == '#') return;
    setState(() {
      px = nx; py = ny;
      final row = map[py].split('');
      if (row[px] == 'E') { score += 100; row[px] = '.'; map[py] = row.join(); energy = (energy + 3).clamp(0, 30); }
      if (row[px] == 'X') { ended = true; won = true; score += energy * 10; }
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(backgroundColor: bg, title: const Text('СЕКТОР 01', style: TextStyle(letterSpacing: 2, fontSize: 13, fontWeight: FontWeight.bold)), leading: IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context, score))),
    body: SafeArea(child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 18),
      child: Column(children: [
        Row(children: [
          _stat('ЭНЕРГИЯ', '$energy сек', cyan),
          const SizedBox(width: 10),
          _stat('ЗАРЯДЫ', '$score', purple),
        ]),
        const SizedBox(height: 16),
        Expanded(child: Center(child: AspectRatio(aspectRatio: 12 / 10, child: CustomPaint(
          painter: MazePainter(map: map, px: px, py: py),
          child: const SizedBox.expand(),
        )))),
        const SizedBox(height: 14),
        const Text('СОБИРАЙ ЭНЕРГОСФЕРЫ  •  ИЩИ ВЫХОД', textAlign: TextAlign.center, style: TextStyle(color: muted, fontSize: 9, letterSpacing: 1.1)),
        const SizedBox(height: 12),
        _controls(),
        const SizedBox(height: 10),
        if (ended) ...[
          Text(won ? 'СЕКТОР ПРОЙДЕН!' : 'ЭНЕРГИЯ ИСЧЕРПАНА', style: TextStyle(color: won ? cyan : purple, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 18)),
          Text('Результат: $score', style: const TextStyle(color: muted)),
          TextButton(onPressed: () => Navigator.pop(context, score), child: const Text('В МЕНЮ')),
        ],
      ]),
    )),
  );

  Widget _stat(String label, String value, Color color) => Expanded(child: Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
    decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(14), border: Border.all(color: color.withOpacity(.18))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: muted, fontSize: 9, letterSpacing: 1.5)),
      const SizedBox(height: 5),
      Text(value, style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.w900)),
    ]),
  ));

  Widget _controls() => Column(children: [
    _arrow(Icons.keyboard_arrow_up_rounded, 0, -1),
    Row(mainAxisAlignment: MainAxisAlignment.center, children: [
      _arrow(Icons.keyboard_arrow_left_rounded, -1, 0),
      const SizedBox(width: 52),
      _arrow(Icons.keyboard_arrow_right_rounded, 1, 0),
    ]),
    _arrow(Icons.keyboard_arrow_down_rounded, 0, 1),
  ]);

  Widget _arrow(IconData icon, int dx, int dy) => Padding(
    padding: const EdgeInsets.all(3),
    child: SizedBox(width: 58, height: 42, child: FilledButton(
      style: FilledButton.styleFrom(backgroundColor: panel, foregroundColor: cyan, padding: EdgeInsets.zero, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: cyan.withOpacity(.25)))),
      onPressed: ended ? null : () => move(dx, dy),
      child: Icon(icon, size: 28),
    )),
  );
}

class MazePainter extends CustomPainter {
  MazePainter({required this.map, required this.px, required this.py});
  final List<String> map;
  final int px, py;
  @override
  void paint(Canvas canvas, Size size) {
    final rows = map.length, cols = map.first.length;
    final cellW = size.width / cols, cellH = size.height / rows;
    final wall = Paint()..color = const Color(0xFF18243A);
    final line = Paint()..color = cyan.withOpacity(.07)..style = PaintingStyle.stroke..strokeWidth = .6;
    final orbGlow = Paint()..color = cyan.withOpacity(.24)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 7);
    for (int y = 0; y < rows; y++) {
      for (int x = 0; x < cols; x++) {
        final rect = Rect.fromLTWH(x * cellW, y * cellH, cellW, cellH).deflate(1);
        canvas.drawRect(rect, line);
        final c = map[y][x];
        if (c == '#') {
          canvas.drawRRect(RRect.fromRectAndRadius(rect.deflate(1), const Radius.circular(4)), wall);
          canvas.drawRRect(RRect.fromRectAndRadius(rect.deflate(1), const Radius.circular(4)), Paint()..color = purple.withOpacity(.16)..style = PaintingStyle.stroke..strokeWidth = 1);
        } else if (c == 'E') {
          final center = rect.center;
          canvas.drawCircle(center, cellW * .28, orbGlow);
          canvas.drawCircle(center, cellW * .16, Paint()..color = cyan);
        } else if (c == 'X') {
          canvas.drawRRect(RRect.fromRectAndRadius(rect.deflate(3), const Radius.circular(5)), Paint()..color = purple.withOpacity(.2));
          final tp = TextPainter(text: const TextSpan(text: 'EXIT', style: TextStyle(color: purple, fontSize: 8, fontWeight: FontWeight.bold)), textDirection: TextDirection.ltr)..layout();
          tp.paint(canvas, Offset(rect.center.dx - tp.width / 2, rect.center.dy - tp.height / 2));
        }
      }
    }
    final center = Offset((px + .5) * cellW, (py + .5) * cellH);
    canvas.drawCircle(center, cellW * .43, Paint()..color = cyan.withOpacity(.15)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 9));
    canvas.drawCircle(center, cellW * .28, Paint()..color = cyan);
    canvas.drawCircle(center, cellW * .12, Paint()..color = bg);
  }
  @override
  bool shouldRepaint(covariant MazePainter old) => old.px != px || old.py != py || old.map != map;
}
