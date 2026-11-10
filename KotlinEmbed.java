import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.commons.ClassRemapper;
import org.objectweb.asm.commons.Remapper;

/**
 * Relocate the Kotlin CLI compiler jar the way kotlin-compiler-embeddable does.
 * The rules match JetBrains' embeddable.kt at tag v2.0.21.
 */
public final class KotlinEmbed {
	private static final Map<String, String> RULES = new LinkedHashMap<>();

	static {
		// protobuf is special: it does not land under com.google.
		RULES.put("com/google/protobuf", "org/jetbrains/kotlin/protobuf");
		RULES.put("com/intellij", "org/jetbrains/kotlin/com/intellij");
		RULES.put("com/google", "org/jetbrains/kotlin/com/google");
		RULES.put("com/sampullara", "org/jetbrains/kotlin/com/sampullara");
		RULES.put("org/apache", "org/jetbrains/kotlin/org/apache");
		RULES.put("org/jdom", "org/jetbrains/kotlin/org/jdom");
		RULES.put("org/picocontainer", "org/jetbrains/kotlin/org/picocontainer");
		RULES.put("org/jline", "org/jetbrains/kotlin/org/jline");
		RULES.put("org/fusesource", "org/jetbrains/kotlin/org/fusesource");
		RULES.put("net/jpountz", "org/jetbrains/kotlin/net/jpountz");
		RULES.put("one/util/streamex", "org/jetbrains/kotlin/one/util/streamex");
		RULES.put("it/unimi/dsi/fastutil", "org/jetbrains/kotlin/it/unimi/dsi/fastutil");
		RULES.put("kotlinx/collections/immutable", "org/jetbrains/kotlin/kotlinx/collections/immutable");
		RULES.put("com/fasterxml", "org/jetbrains/kotlin/com/fasterxml");
		RULES.put("org/codehaus", "org/jetbrains/kotlin/org/codehaus");
		RULES.put("javax/inject", "org/jetbrains/kotlin/javax/inject");
	}

	public static void main(String[] args) throws IOException {
		if (args.length != 2) {
			System.err.println("usage: KotlinEmbed INPUT.jar OUTPUT.jar");
			System.exit(2);
		}
		relocate(args[0], args[1]);
	}

	static void relocate(String input, String output) throws IOException {
		EmbedRemapper remapper = new EmbedRemapper();
		int classes = 0;
		int dropped = 0;
		try (ZipFile zip = new ZipFile(input);
			 ZipOutputStream out = new ZipOutputStream(new java.io.FileOutputStream(output))) {
			Set<String> written = new HashSet<>();
			var entries = zip.entries();
			while (entries.hasMoreElements()) {
				ZipEntry entry = entries.nextElement();
				String name = entry.getName();
				if (name.endsWith("/")) {
					continue;
				}
				if (drop(name)) {
					dropped++;
					continue;
				}
				byte[] data = readAll(zip.getInputStream(entry));
				String mappedName = remapPath(name);
				if (name.endsWith("com/intellij/util/lang/JavaVersion.class")) {
					data = widenJavaVersionCeiling(data);
				}
				if (name.endsWith(".class")) {
					data = remapClass(data, remapper);
					classes++;
					if (classes % 5000 == 0) {
						System.err.println("classes " + classes);
					}
				} else if (rewriteText(name)) {
					data = remapText(data);
				}
				if (!written.add(mappedName)) {
					continue;
				}
				ZipEntry dest = new ZipEntry(mappedName);
				dest.setTime(entry.getTime());
				out.putNextEntry(dest);
				out.write(data);
				out.closeEntry();
			}
		}
		System.err.println("classes " + classes + " dropped " + dropped);
	}

	private static boolean drop(String name) {
		String rest = stripVersion(name);
		if (rest.startsWith("com/sun/jna/")) {
			return true;
		}
		if (rest.startsWith("org/jetbrains/annotations/")) {
			return true;
		}
		if (name.startsWith("META-INF/native-image/")) {
			return true;
		}
		if (name.startsWith("META-INF/") && (name.endsWith(".SF") || name.endsWith(".RSA") || name.endsWith(".DSA"))) {
			return true;
		}
		return false;
	}

	private static boolean rewriteText(String name) {
		if (name.startsWith("META-INF/services/")) {
			return true;
		}
		if (name.endsWith(".xml") || name.endsWith(".properties") || name.equals("META-INF/MANIFEST.MF")) {
			return true;
		}
		return false;
	}

	/**
	 * Kotlin 2.0's bundled IntelliJ parser accepts feature versions 5 through 24.
	 * OpenMandriva's JDK 25 and 27 report versions such as 27.0.1.0.3-internal,
	 * so the compiler throws before it can read the platform modules.
	 * The modern parser already understands that shape. Raise the ceiling from
	 * 25 to 127 without changing instruction lengths.
	 */
	static byte[] widenJavaVersionCeiling(byte[] data) {
		byte[] out = data.clone();
		byte[] modern = new byte[] {0x10, 0x19, (byte) 0xA2};
		int hits = 0;
		for (int i = 0; i + modern.length <= out.length; i++) {
			if (out[i] == modern[0] && out[i + 1] == modern[1] && out[i + 2] == modern[2]) {
				out[i + 1] = 0x7F;
				hits++;
			}
		}
		if (hits != 1) {
			throw new IllegalStateException("JavaVersion ceiling patch matched " + hits + " sites");
		}
		return out;
	}

	private static byte[] remapClass(byte[] data, EmbedRemapper remapper) {
		ClassReader reader = new ClassReader(data);
		ClassWriter writer = new ClassWriter(0);
		try {
			reader.accept(new ClassRemapper(writer, remapper), ClassReader.EXPAND_FRAMES);
		} catch (RuntimeException first) {
			writer = new ClassWriter(0);
			try {
				reader.accept(new ClassRemapper(writer, remapper), 0);
			} catch (RuntimeException second) {
				throw new IllegalStateException("remap failed for " + reader.getClassName(), second);
			}
		}
		return writer.toByteArray();
	}

	private static byte[] remapText(byte[] data) {
		String text = new String(data, StandardCharsets.UTF_8);
		String mapped = mapDottedText(text);
		if (mapped.contains("Implementation-Title: kotlin-compiler")) {
			mapped = mapped.replace("Implementation-Title: kotlin-compiler",
				"Implementation-Title: kotlin-compiler-embeddable");
		}
		return mapped.getBytes(StandardCharsets.UTF_8);
	}

	static String remapPath(String name) {
		String prefix = "";
		String rest = name;
		if (name.startsWith("META-INF/versions/")) {
			int slash = name.indexOf('/', "META-INF/versions/".length());
			if (slash > 0) {
				prefix = name.substring(0, slash + 1);
				rest = name.substring(slash + 1);
			}
		} else if (name.startsWith("META-INF/services/") && name.indexOf('/', "META-INF/services/".length()) > 0) {
			prefix = "META-INF/services/";
			rest = name.substring(prefix.length());
		}
		if (keepPath(rest)) {
			return name;
		}
		String mapped = mapInternal(rest);
		if (mapped.equals(rest)) {
			return name;
		}
		return prefix + mapped;
	}

	private static boolean keepPath(String rest) {
		return rest.equals("org/fusesource/jansi/internal/CLibrary.class")
			|| rest.startsWith("org/fusesource/jansi/internal/CLibrary$")
			|| rest.startsWith("org/fusesource/jansi/internal/native/");
	}

	static String mapInternal(String internal) {
		if (internal == null || internal.isEmpty()) {
			return internal;
		}
		if (internal.equals("org/fusesource/jansi/internal/CLibrary")
			|| internal.startsWith("org/fusesource/jansi/internal/CLibrary$")) {
			return internal;
		}
		for (Map.Entry<String, String> rule : RULES.entrySet()) {
			String from = rule.getKey();
			if (internal.equals(from) || internal.startsWith(from + "/")) {
				return rule.getValue() + internal.substring(from.length());
			}
		}
		return internal;
	}

	static String mapDottedText(String text) {
		StringBuilder out = new StringBuilder(text.length());
		int i = 0;
		while (i < text.length()) {
			int start = i;
			char c = text.charAt(i);
			if (Character.isJavaIdentifierStart(c)) {
				i++;
				while (i < text.length()) {
					char d = text.charAt(i);
					if (Character.isJavaIdentifierPart(d) || d == '.') {
						i++;
					} else {
						break;
					}
				}
				out.append(mapDottedToken(text.substring(start, i)));
			} else {
				out.append(c);
				i++;
			}
		}
		return out.toString();
	}

	private static String mapDottedToken(String token) {
		if (token.equals("com.intellij.projectService") || token.equals("com.intellij.applicationService")) {
			return token;
		}
		String internal = token.replace('.', '/');
		String mapped = mapInternal(internal);
		if (mapped.equals(internal)) {
			return token;
		}
		return mapped.replace('/', '.');
	}

	private static String stripVersion(String name) {
		if (!name.startsWith("META-INF/versions/")) {
			return name;
		}
		int slash = name.indexOf('/', "META-INF/versions/".length());
		if (slash < 0) {
			return name;
		}
		return name.substring(slash + 1);
	}

	private static byte[] readAll(InputStream in) throws IOException {
		try (in) {
			ByteArrayOutputStream buf = new ByteArrayOutputStream();
			in.transferTo(buf);
			return buf.toByteArray();
		}
	}

	private static final class EmbedRemapper extends Remapper {
		@Override
		public String map(String internalName) {
			return mapInternal(internalName);
		}

		@Override
		public Object mapValue(Object value) {
			if (!(value instanceof String text)) {
				return super.mapValue(value);
			}
			if (text.indexOf('.') < 0 && text.indexOf('/') < 0) {
				return text;
			}
			if (text.indexOf('/') >= 0 && text.indexOf(' ') < 0 && text.indexOf('\n') < 0) {
				String mapped = mapInternal(text);
				if (!mapped.equals(text)) {
					return mapped;
				}
			}
			if (text.indexOf('.') >= 0 && text.indexOf(' ') < 0 && text.indexOf('\n') < 0 && text.length() < 500) {
				return mapDottedToken(text);
			}
			return text;
		}
	}
}
