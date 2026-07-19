import 'dart:ui';

import 'package:flutter/material.dart';

class GlassPanel extends StatelessWidget {
  const GlassPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
    this.radius = 28,
    this.opacity = .58,
  });

  final Widget child;
  final EdgeInsets padding;
  final double radius;
  final double opacity;

  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: BorderRadius.circular(radius),
    child: BackdropFilter(
      filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: opacity),
          borderRadius: BorderRadius.circular(radius),
          border: Border.all(color: Colors.white.withValues(alpha: .74)),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF314037).withValues(alpha: .08),
              blurRadius: 36,
              offset: const Offset(0, 18),
            ),
          ],
        ),
        child: Padding(padding: padding, child: child),
      ),
    ),
  );
}

class AmbientBackground extends StatelessWidget {
  const AmbientBackground({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Stack(
    fit: StackFit.expand,
    children: [
      const ColoredBox(color: Color(0xFFF2F0E9)),
      const Positioned(
        top: -80,
        right: -80,
        child: _Glow(color: Color(0xFFC6F0D8), size: 300),
      ),
      const Positioned(
        top: 230,
        left: -120,
        child: _Glow(color: Color(0xFFD6CDFB), size: 290),
      ),
      const Positioned(
        bottom: -120,
        right: -80,
        child: _Glow(color: Color(0xFFFFC4AA), size: 320),
      ),
      child,
    ],
  );
}

class _Glow extends StatelessWidget {
  const _Glow({required this.color, required this.size});
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) => ImageFiltered(
    imageFilter: ImageFilter.blur(sigmaX: 46, sigmaY: 46),
    child: Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color.withValues(alpha: .78),
        shape: BoxShape.circle,
      ),
    ),
  );
}
