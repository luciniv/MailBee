/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
SET @MYSQLDUMP_TEMP_LOG_BIN = @@SESSION.SQL_LOG_BIN;
SET @@SESSION.SQL_LOG_BIN= 0;

--
-- GTID state at the beginning of the backup 
--

SET @@GLOBAL.GTID_PURGED=/*!80000 '+'*/ '23f80100-7a93-11f0-a05c-d22291bca3de:1-18052,
3c3cfa69-060c-11f0-90f9-f2150993146a:1-47024,
6c5093d6-e325-11ef-a0b9-121de2a0b8af:1-1827';

--
-- Table structure for table `ap_adjs`
--

DROP TABLE IF EXISTS `ap_adjs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ap_adjs` (
  `adjID` int NOT NULL AUTO_INCREMENT,
  `adj` varchar(32) NOT NULL,
  PRIMARY KEY (`adjID`)
) ENGINE=InnoDB AUTO_INCREMENT=244 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ap_links`
--

DROP TABLE IF EXISTS `ap_links`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ap_links` (
  `guildID` bigint NOT NULL,
  `modID` bigint NOT NULL,
  `adjID` int DEFAULT NULL,
  `nounID` int DEFAULT NULL,
  `date` bigint NOT NULL,
  PRIMARY KEY (`guildID`,`modID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ap_nouns`
--

DROP TABLE IF EXISTS `ap_nouns`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ap_nouns` (
  `nounID` int NOT NULL AUTO_INCREMENT,
  `guildID` bigint NOT NULL,
  `noun` varchar(32) NOT NULL,
  `nounURL` text,
  PRIMARY KEY (`nounID`,`guildID`)
) ENGINE=InnoDB AUTO_INCREMENT=402 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `blacklist`
--

DROP TABLE IF EXISTS `blacklist`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `blacklist` (
  `guildID` bigint NOT NULL,
  `userID` bigint NOT NULL,
  `reason` text,
  `modID` bigint DEFAULT NULL,
  `modName` varchar(32) DEFAULT NULL,
  `date` bigint DEFAULT NULL,
  PRIMARY KEY (`guildID`,`userID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `config`
--

DROP TABLE IF EXISTS `config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `config` (
  `guildID` bigint NOT NULL,
  `logID` bigint DEFAULT NULL,
  `inboxID` bigint DEFAULT NULL,
  `responsesID` bigint DEFAULT NULL,
  `feedbackID` bigint DEFAULT NULL,
  `reportID` bigint DEFAULT NULL,
  `greeting` text,
  `closing` text,
  `accepting` text,
  `anon` enum('true','false') NOT NULL DEFAULT 'true',
  `blacklisted` enum('true','false') NOT NULL DEFAULT 'false',
  `analytics` enum('true','false') NOT NULL DEFAULT 'false',
  `logging` enum('true','false') NOT NULL DEFAULT 'false',
  `aps` enum('true','false') NOT NULL DEFAULT 'false',
  PRIMARY KEY (`guildID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `notes`
--

DROP TABLE IF EXISTS `notes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notes` (
  `noteID` int NOT NULL AUTO_INCREMENT,
  `guildID` bigint NOT NULL,
  `userID` bigint DEFAULT NULL,
  `ticketID` bigint DEFAULT NULL,
  `authorID` bigint NOT NULL,
  `authorName` varchar(32) NOT NULL,
  `date` bigint NOT NULL,
  `content` text NOT NULL,
  PRIMARY KEY (`noteID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `permissions`
--

DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `permissions` (
  `guildID` bigint NOT NULL,
  `roleID` bigint NOT NULL,
  `permLevel` varchar(64) NOT NULL,
  PRIMARY KEY (`roleID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `snips`
--

DROP TABLE IF EXISTS `snips`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `snips` (
  `guildID` bigint NOT NULL,
  `authorID` bigint NOT NULL,
  `abbrev` varchar(24) NOT NULL,
  `summary` text NOT NULL,
  `content` text NOT NULL,
  `date` bigint NOT NULL,
  PRIMARY KEY (`guildID`,`abbrev`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ticket_messages_v2`
--

DROP TABLE IF EXISTS `ticket_messages_v2`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_messages_v2` (
  `channelID` bigint NOT NULL,
  `messageID` bigint NOT NULL,
  `authorID` bigint NOT NULL,
  `date` timestamp NOT NULL,
  `type` varchar(32) NOT NULL,
  PRIMARY KEY (`messageID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ticket_types`
--

DROP TABLE IF EXISTS `ticket_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_types` (
  `typeID` int NOT NULL AUTO_INCREMENT,
  `guildID` bigint DEFAULT NULL,
  `categoryID` bigint DEFAULT NULL,
  `typeName` varchar(100) DEFAULT NULL,
  `typeDescrip` varchar(100) DEFAULT NULL,
  `typeEmoji` varchar(100) DEFAULT NULL,
  `formJson` text,
  `subType` bigint NOT NULL DEFAULT '-1',
  `redirectText` text,
  `NSFWCategoryID` bigint NOT NULL DEFAULT '-1',
  `pingRoles` text,
  PRIMARY KEY (`typeID`)
) ENGINE=InnoDB AUTO_INCREMENT=179 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tickets_v2`
--

DROP TABLE IF EXISTS `tickets_v2`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tickets_v2` (
  `guildID` bigint NOT NULL,
  `ticketID` int NOT NULL DEFAULT '-1',
  `channelID` bigint NOT NULL,
  `logID` bigint DEFAULT NULL,
  `dateOpen` timestamp NOT NULL,
  `dateClose` timestamp NULL DEFAULT NULL,
  `openerID` bigint NOT NULL,
  `closerID` bigint DEFAULT NULL,
  `closerUN` varchar(32) DEFAULT NULL,
  `state` enum('open','closed') NOT NULL DEFAULT 'open',
  `type` int NOT NULL DEFAULT '1',
  `time` int NOT NULL,
  `queue` int NOT NULL DEFAULT '0',
  `rating` text,
  `robux` int NOT NULL DEFAULT '-1',
  `hours` float NOT NULL DEFAULT '-1',
  PRIMARY KEY (`channelID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `verbals`
--

DROP TABLE IF EXISTS `verbals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `verbals` (
  `messageID` bigint NOT NULL,
  `guildID` bigint NOT NULL,
  `userID` bigint NOT NULL,
  `authorID` bigint NOT NULL,
  `authorName` varchar(32) NOT NULL,
  `date` bigint NOT NULL,
  `content` text NOT NULL,
  PRIMARY KEY (`messageID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-09-26 20:48:39
