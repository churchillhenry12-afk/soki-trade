package code.soki.mobile.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CameraAlt
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

@Composable
fun PairingScanner(
    onScanned: (String) -> Unit,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    var permissionGranted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> permissionGranted = granted }

    LaunchedEffect(Unit) {
        if (!permissionGranted) permissionLauncher.launch(Manifest.permission.CAMERA)
    }

    Box(Modifier.fillMaxSize().background(Ink)) {
        if (permissionGranted) {
            CameraSurface(onScanned)
        } else {
            Column(
                modifier = Modifier.align(Alignment.Center).padding(36.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Icon(Icons.Rounded.CameraAlt, null, tint = Paper, modifier = Modifier.size(34.dp))
                Text(
                    "Camera access is needed to scan the one-time laptop code.",
                    color = Paper,
                    fontSize = 15.sp,
                    lineHeight = 22.sp,
                )
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(18.dp, 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back", tint = Paper)
            }
            Text(
                "PAIR LAPTOP",
                color = Paper,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.sp,
            )
        }

        Box(
            modifier = Modifier
                .align(Alignment.Center)
                .size(264.dp)
                .border(2.dp, Cobalt, RoundedCornerShape(24.dp)),
        )
        Column(
            modifier = Modifier.align(Alignment.BottomCenter).padding(30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Place the full code inside the frame", color = Paper, fontWeight = FontWeight.SemiBold)
            Text(
                "The scan is processed on this phone.",
                color = Color(0xFFAAB4B8),
                fontSize = 11.sp,
                modifier = Modifier.padding(top = 5.dp),
            )
        }
    }
}

@ExperimentalGetImage
@Composable
private fun CameraSurface(onScanned: (String) -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val executor = remember { Executors.newSingleThreadExecutor() }
    val handled = remember { AtomicBoolean(false) }
    val scanner = remember {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .build(),
        )
    }

    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { previewContext ->
            PreviewView(previewContext).apply {
                scaleType = PreviewView.ScaleType.FILL_CENTER
                implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                val providerFuture = ProcessCameraProvider.getInstance(previewContext)
                providerFuture.addListener(
                    {
                        val provider = providerFuture.get()
                        val preview = Preview.Builder().build().also {
                            it.surfaceProvider = surfaceProvider
                        }
                        val analysis = ImageAnalysis.Builder()
                            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                            .build()
                        analysis.setAnalyzer(executor) { proxy ->
                            val mediaImage = proxy.image
                            if (mediaImage == null || handled.get()) {
                                proxy.close()
                                return@setAnalyzer
                            }
                            val image = InputImage.fromMediaImage(
                                mediaImage,
                                proxy.imageInfo.rotationDegrees,
                            )
                            scanner.process(image)
                                .addOnSuccessListener { barcodes ->
                                    val raw = barcodes.firstOrNull()?.rawValue
                                    if (!raw.isNullOrBlank() && handled.compareAndSet(false, true)) {
                                        onScanned(raw)
                                    }
                                }
                                .addOnCompleteListener { proxy.close() }
                        }
                        provider.unbindAll()
                        provider.bindToLifecycle(
                            lifecycleOwner,
                            CameraSelector.DEFAULT_BACK_CAMERA,
                            preview,
                            analysis,
                        )
                    },
                    ContextCompat.getMainExecutor(previewContext),
                )
            }
        },
    )

    DisposableEffect(Unit) {
        onDispose {
            scanner.close()
            executor.shutdown()
            ProcessCameraProvider.getInstance(context).get().unbindAll()
        }
    }
}
