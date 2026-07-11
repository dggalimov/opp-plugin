// Читает MS Project (.mpp/.mpx/…) через MPXJ и печатает задачи (имя · старт · финиш).
// Запускается отдельным процессом java (не через JPype: системный Python может не дать JVM память).
import org.mpxj.ProjectFile;
import org.mpxj.Task;
import org.mpxj.reader.UniversalProjectReader;

public class MppRead {
    public static void main(String[] args) throws Exception {
        ProjectFile project = new UniversalProjectReader().read(args[0]);
        if (project == null) { System.err.println("MPXJ: формат не распознан"); return; }
        for (Task t : project.getTasks()) {
            String nm = t.getName();
            if (nm == null || nm.isEmpty()) continue;
            Integer lvl = t.getOutlineLevel();
            int indent = (lvl == null ? 0 : Math.max(0, lvl - 1));
            StringBuilder pad = new StringBuilder();
            for (int i = 0; i < indent; i++) pad.append("  ");
            System.out.println(pad + "- " + nm + "  [" + t.getStart() + " → " + t.getFinish() + "]");
        }
    }
}
