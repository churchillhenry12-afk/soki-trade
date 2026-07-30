package code.soki.mobile.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Ink = Color(0xFF202124)
val Paper = Color(0xFFFFFFFF)
val Ground = Color(0xFFF4F4F2)
val Cobalt = Color(0xFF315CF5)
val Coral = Color(0xFF315CF5)
val Jade = Color(0xFF16806F)
val Amber = Color(0xFFB87722)
val Danger = Color(0xFFB84040)
val Muted = Color(0xFF72757B)
val Hairline = Color(0xFFE4E5E2)

private val colors = lightColorScheme(
    primary = Cobalt,
    onPrimary = Color.White,
    secondary = Coral,
    onSecondary = Color.White,
    tertiary = Jade,
    background = Ground,
    onBackground = Ink,
    surface = Paper,
    onSurface = Ink,
    outline = Hairline,
    error = Danger,
)

private val typography = Typography(
    displayLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 32.sp,
        lineHeight = 36.sp,
        letterSpacing = (-1.2).sp,
    ),
    headlineLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 26.sp,
        lineHeight = 30.sp,
        letterSpacing = (-0.8).sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 18.sp,
        lineHeight = 22.sp,
        letterSpacing = (-0.4).sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 15.sp,
        lineHeight = 23.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 13.sp,
        lineHeight = 20.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Medium,
        fontSize = 9.sp,
        letterSpacing = 1.1.sp,
    ),
)

@Composable
fun SokiTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = colors,
        typography = typography,
        content = content,
    )
}
